locals {
  lab_name = "vwan-ipsec-over-er-backup"
  prefix   = "ver-${var.run_id}"

  tags = {
    lab            = "true"
    lab_name       = local.lab_name
    created_by     = "copilot-lab"
    owner          = "jose"
    ephemeral      = "true"
    run_id         = var.run_id
    correlation_id = var.run_id
  }
}
