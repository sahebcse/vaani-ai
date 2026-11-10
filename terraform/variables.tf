variable "region" {
  description = "AWS region for the Vaani stack."
  type        = string
  default     = "ap-south-1"
}

variable "project" {
  description = "Name prefix for all resources."
  type        = string
  default     = "vaani"
}

variable "app_image" {
  description = "vaani-app container image (ECR URI + tag)."
  type        = string
}

variable "mock_image" {
  description = "mock-sarvam container image (ECR URI + tag)."
  type        = string
}
