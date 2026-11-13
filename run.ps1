param(
  [Parameter(Position=0)][string]$Task = "help",
  [Parameter(ValueFromRemainingArguments=$true)][string[]]$Rest
)

switch ($Task) {
  "seo"    { python seo/run.py @Rest }
  "serp"   { python core/serp.py @Rest }
  "credit" { curl.exe https://api.kie.ai/api/v1/chat/credit -H "Authorization: Bearer $env:KIE_API_KEY" }
  "models" { curl.exe https://api.kie.ai/openai/v1/models  -H "Authorization: Bearer $env:KIE_API_KEY" }
  "vendor" { powershell -NoProfile -File .\setup.ps1 -VendorOnly }
  default  { Write-Host "использование: .\run.ps1 seo|serp|credit|models|vendor [аргументы]" }
}
