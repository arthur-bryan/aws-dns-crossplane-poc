aws_export_creds() {
  local creds key secret
  creds=$(kubectl -n crossplane-system get secret aws-creds -o jsonpath='{.data.credentials}' | base64 -d)
  key=$(printf '%s\n' "$creds" | grep aws_access_key_id     | awk -F'= ' '{print $2}' | tr -d '[:space:]')
  secret=$(printf '%s\n' "$creds" | grep aws_secret_access_key | awk -F'= ' '{print $2}' | tr -d '[:space:]')
  export AWS_ACCESS_KEY_ID="$key"
  export AWS_SECRET_ACCESS_KEY="$secret"
  export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
}
