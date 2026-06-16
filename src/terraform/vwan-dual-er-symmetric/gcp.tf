###############################################################################
# GCP on-prem simulation — Design B (single shared GLOBAL-routing VPC)        #
# - One VPC (vpc_a, eu-w3, GLOBAL routing) serves both regions                #
# - Two Cloud Routers: router_a (eu-w3/MCR1) + cr_onprem_b (eu-w4/MCR2)      #
#   Both CRs advertise both GCP subnets for automatic failover                #
# - Two PARTNER attachments: att_a (eu-w3, unchanged) + att_b_new (eu-w4)    #
# - One VM per region: vm_a (eu-w3, unchanged) + vm_b (eu-w4, in vpc_a)      #
###############################################################################

# ----------------------------- VPC A -----------------------------------------

resource "google_compute_network" "vpc_a" {
  name                    = "vpc-${var.lab_name}-a-${local.correlation_id}"
  auto_create_subnetworks = false
  routing_mode            = "GLOBAL"
}

resource "google_compute_subnetwork" "vpc_a_subnet" {
  name          = "subnet-${var.lab_name}-a"
  ip_cidr_range = var.gcp_vpc_a_subnet
  region        = var.gcp_region_a
  network       = google_compute_network.vpc_a.id
}

resource "google_compute_firewall" "vpc_a_allow" {
  name    = "fw-${var.lab_name}-a-allow"
  network = google_compute_network.vpc_a.name

  allow {
    protocol = "all"
  }

  source_ranges = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "35.235.240.0/20"]
}

resource "google_compute_router" "router_a" {
  name    = "router-${var.lab_name}-a"
  region  = var.gcp_region_a
  network = google_compute_network.vpc_a.name

  bgp {
    asn               = var.gcp_cloud_router_asn_a
    advertise_mode    = "CUSTOM"
    advertised_groups = []

    advertised_ip_ranges {
      range       = var.gcp_vpc_a_subnet
      description = "Region A on-prem subnet only"
    }

    advertised_ip_ranges {
      range       = var.gcp_vpc_b_subnet
      description = "Region B GCP subnet (via GLOBAL VPC routing — failover path)"
    }
  }
}

resource "google_compute_interconnect_attachment" "att_a" {
  name                     = "att-${var.lab_name}-a"
  region                   = var.gcp_region_a
  router                   = google_compute_router.router_a.id
  type                     = "PARTNER"
  edge_availability_domain = "AVAILABILITY_DOMAIN_1"
  admin_enabled            = true
}

resource "google_compute_instance" "vm_a" {
  name         = "vm-${var.lab_name}-a"
  machine_type = var.gcp_vm_machine_type
  zone         = "${var.gcp_region_a}-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 10
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.vpc_a_subnet.id
  }

  metadata_startup_script = <<-EOT
    #!/bin/bash
    apt-get update -y
    apt-get install -y nginx curl traceroute
    echo "gcp-vpc-a ready ($(hostname))" > /var/www/html/index.html
    systemctl enable --now nginx
  EOT

  tags = ["onprem-sim"]
}

# ----------------------------- VPC B (REMOVED in Design B) -------------------
# vpc_b, vpc_b_subnet, vpc_b_allow, router_b, att_b destroyed.
# Replaced by: vpc_onprem_subnet_b + cr_onprem_b + att_b_new (all in vpc_a).

# ----------------------------- eu-w4 subnet in vpc_a -------------------------

resource "google_compute_subnetwork" "vpc_onprem_subnet_b" {
  provider      = google.region_b
  name          = "subnet-${var.lab_name}-onprem-b"
  ip_cidr_range = var.gcp_vpc_b_subnet
  region        = var.gcp_region_b
  network       = google_compute_network.vpc_a.id
}

# Design C (2026-06-15): cr_onprem_b + att_b_new REMOVED.
# Both were Design B eu-w4 resources. Destroyed in Phase 1B after BGP
# convergence verified on att_b_v2 (eu-w3, router_a). See Phase 1B evidence:
# labs/vwan-dual-er-symmetric/show-output/design-c-phase1b-2026-06-15/

# ----------------------------- Design C consolidation -------------------------
# Design C (2026-06-15): single-CR on-prem simulation per Jose's directive.
# Both Interconnect attachments terminate on router_a (eu-w3). att_b_v2
# is the eu-w3 replacement for att_b_new (eu-w4). Megaport-side VXC gcp_b
# will be re-paired manually by Jose in the portal (account lock prevents
# TF-driven re-pair). att_b_new + cr_onprem_b destroyed in Phase 1B after
# BGP convergence on the new path is verified.

resource "google_compute_interconnect_attachment" "att_b_v2" {
  name                     = "att-${var.lab_name}-b-v2"
  region                   = var.gcp_region_a              # eu-w3, same region as router_a
  router                   = google_compute_router.router_a.id
  type                     = "PARTNER"
  edge_availability_domain = "AVAILABILITY_DOMAIN_2"        # different domain from att_a's DOMAIN_1 for edge diversity
  admin_enabled            = true
}

resource "google_compute_instance" "vm_b" {
  provider     = google.region_b
  name         = "vm-${var.lab_name}-b"
  machine_type = var.gcp_vm_machine_type
  zone         = "${var.gcp_region_b}-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 10
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.vpc_onprem_subnet_b.id
  }

  metadata_startup_script = <<-EOT
    #!/bin/bash
    apt-get update -y
    apt-get install -y nginx curl traceroute
    echo "gcp-vpc-b ready ($(hostname))" > /var/www/html/index.html
    systemctl enable --now nginx
  EOT

  tags = ["onprem-sim"]
}
