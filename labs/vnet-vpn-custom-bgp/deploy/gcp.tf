resource "google_project" "lab" {
  project_id          = local.gcp_project
  name                = local.gcp_project
  billing_account     = var.billing_account
  auto_create_network = false
  deletion_policy     = "DELETE"
  labels              = local.tags
}

resource "google_project_service" "lab" {
  for_each = toset([
    "compute.googleapis.com",
    "serviceusage.googleapis.com",
    "cloudresourcemanager.googleapis.com"
  ])
  project            = google_project.lab.project_id
  service            = each.key
  disable_on_destroy = false
}

resource "google_compute_network" "lab" {
  name                    = "vpc-${local.prefix}"
  auto_create_subnetworks = false
  routing_mode            = "GLOBAL"
  depends_on              = [google_project_service.lab]
}

resource "google_compute_subnetwork" "lab" {
  name          = "subnet-${local.prefix}"
  region        = "europe-north2"
  network       = google_compute_network.lab.id
  ip_cidr_range = "10.245.0.0/24"
  secondary_ip_range {
    range_name    = "bgp-identities"
    ip_cidr_range = "10.245.254.0/24"
  }
  secondary_ip_range {
    range_name    = "overlay-payload"
    ip_cidr_range = "10.246.1.0/24"
  }
}

resource "google_compute_router" "lab" {
  name    = "cr-${local.prefix}"
  region  = "europe-north2"
  network = google_compute_network.lab.id
  bgp {
    asn            = 16550
    advertise_mode = "CUSTOM"
    advertised_ip_ranges {
      range       = "10.245.0.10/32"
      description = "Private IPsec outer endpoint only; never overlay payload."
    }
  }
}

resource "google_compute_interconnect_attachment" "lab" {
  name                     = "att-${local.prefix}"
  region                   = "europe-north2"
  router                   = google_compute_router.lab.id
  type                     = "PARTNER"
  edge_availability_domain = "AVAILABILITY_DOMAIN_1"
  admin_enabled            = true
}

resource "google_compute_address" "cpe" {
  name   = "pip-${local.prefix}"
  region = "europe-north2"
}

resource "google_compute_firewall" "ike" {
  name    = "ike-${local.prefix}"
  network = google_compute_network.lab.name
  allow {
    protocol = "udp"
    ports    = ["500", "4500"]
  }
  allow {
    protocol = "esp"
  }
  source_ranges = [
    for key in ["vpn0", "vpn1"] : "${azurerm_public_ip.gateway[key].ip_address}/32"
  ]
  target_tags = ["ipsec-cpe"]
}

resource "google_compute_firewall" "private" {
  name    = "private-${local.prefix}"
  network = google_compute_network.lab.name
  allow {
    protocol = "udp"
    ports    = ["500", "4500"]
  }
  allow {
    protocol = "esp"
  }
  allow {
    protocol = "icmp"
  }
  allow {
    protocol = "tcp"
    ports    = ["179", "8080"]
  }
  source_ranges = ["10.244.0.0/16"]
  target_tags   = ["ipsec-cpe"]
}

resource "google_compute_firewall" "iap" {
  name          = "iap-${local.prefix}"
  network       = google_compute_network.lab.name
  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["ipsec-cpe"]
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

resource "google_compute_instance" "cpe" {
  name                      = "cpe-${local.prefix}"
  zone                      = "europe-north2-a"
  machine_type              = "e2-small"
  can_ip_forward            = true
  allow_stopping_for_update = true
  tags                      = ["ipsec-cpe"]
  labels                    = local.tags
  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = 20
      type  = "pd-standard"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.lab.id
    network_ip = "10.245.0.10"
    alias_ip_range {
      ip_cidr_range         = "10.245.254.6/32"
      subnetwork_range_name = "bgp-identities"
    }
    alias_ip_range {
      ip_cidr_range         = "10.246.1.1/32"
      subnetwork_range_name = "overlay-payload"
    }
    access_config {
      nat_ip = google_compute_address.cpe.address
    }
  }
  metadata = {
    startup-script = file("${path.module}/../../../src/terraform/vwan-ipsec-over-er-backup/cpe-startup.sh")
  }
}
