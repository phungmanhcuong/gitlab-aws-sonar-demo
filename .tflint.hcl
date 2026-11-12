# Built-in Terraform rules only (no cloud plugin download in CI).
plugin "terraform" {
  enabled = true
  preset  = "recommended"
}
