output "alb_dns" {
  description = "Public endpoint for the Vaani app."
  value       = aws_lb.app.dns_name
}

output "opensearch_endpoint" {
  description = "OpenSearch domain endpoint for the RAG store."
  value       = aws_opensearch_domain.main.endpoint
}

output "rds_endpoint" {
  description = "Postgres endpoint for the call warehouse."
  value       = aws_db_instance.main.endpoint
}
