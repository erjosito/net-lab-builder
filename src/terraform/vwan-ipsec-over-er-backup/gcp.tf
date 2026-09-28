resource "google_compute_network" "lab" {
  name                    = "vpc-${local.prefix}"
  auto_create_subnetworks = false
  routing_mode            = "GLOBAL"
}

resource "google_compute_subnetwork" "lab" {
  name          = "subnet-${local.prefix}"
  region        = var.gcp_region
  network       = google_compute_network.lab.id
  ip_cidr_range = "10.250.0.0/24"

  secondary_ip_range {
    range_name    = "cpe-peer-identities"
    ip_cidr_range = "10.250.254.0/24"
  }
}

resource "google_compute_router" "lab" {
  name    = "cr-${local.prefix}"
  region  = var.gcp_region
  network = google_compute_network.lab.id

  bgp {
    asn            = 16550
    advertise_mode = "CUSTOM"

    advertised_ip_ranges {
      range       = "10.250.0.10/32"
      description = "Private CPE endpoint only"
    }
  }
}

resource "google_compute_interconnect_attachment" "lab" {
  name                     = "att-${local.prefix}"
  region                   = var.gcp_region
  router                   = google_compute_router.lab.id
  type                     = "PARTNER"
  edge_availability_domain = "AVAILABILITY_DOMAIN_1"
  admin_enabled            = true
}

resource "google_compute_address" "cpe" {
  name   = "pip-cpe-${local.prefix}"
  region = var.gcp_region
}

resource "google_compute_resource_policy" "cpe_stop" {
  name   = "stop-cpe-${local.prefix}"
  region = var.gcp_region

  instance_schedule_policy {
    time_zone = "Europe/Stockholm"

    vm_stop_schedule {
      schedule = "0 23 * * *"
    }
  }
}

resource "google_compute_firewall" "ike" {
  name    = "fw-ike-${local.prefix}"
  network = google_compute_network.lab.name

  allow {
    protocol = "udp"
    ports    = ["500", "4500"]
  }

  allow {
    protocol = "esp"
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["ipsec-cpe"]
}

resource "google_compute_firewall" "lab_private" {
  name    = "fw-private-${local.prefix}"
  network = google_compute_network.lab.name

  allow {
    protocol = "icmp"
  }

  allow {
    protocol = "tcp"
    ports    = ["179", "22"]
  }

  source_ranges = ["10.240.0.0/15", "10.250.0.0/16", "10.253.0.0/16", "35.235.240.0/20"]
  target_tags   = ["ipsec-cpe"]
}

resource "google_compute_instance" "cpe" {
  name                      = "cpe-${local.prefix}"
  zone                      = var.gcp_zone
  machine_type              = var.gcp_machine_type
  can_ip_forward            = true
  allow_stopping_for_update = true
  tags                      = ["ipsec-cpe"]
  resource_policies         = [google_compute_resource_policy.cpe_stop.self_link]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = 20
      type  = "pd-balanced"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.lab.id
    network_ip = "10.250.0.10"
    alias_ip_range {
      ip_cidr_range         = "10.250.254.240/32"
      subnetwork_range_name = "cpe-peer-identities"
    }
    alias_ip_range {
      ip_cidr_range         = "10.250.254.241/32"
      subnetwork_range_name = "cpe-peer-identities"
    }
    alias_ip_range {
      ip_cidr_range         = "10.250.254.242/32"
      subnetwork_range_name = "cpe-peer-identities"
    }
    alias_ip_range {
      ip_cidr_range         = "10.250.254.250/32"
      subnetwork_range_name = "cpe-peer-identities"
    }
    access_config {
      nat_ip = google_compute_address.cpe.address
    }
  }

  metadata = {
    ssh-keys       = "azurelabuser:${var.ssh_public_key}"
    startup-script = file("${path.module}/cpe-startup.sh")
  }
}
