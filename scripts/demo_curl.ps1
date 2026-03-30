$ErrorActionPreference = "Stop"

$BASE_URL = $env:BASE_URL
if (-not $BASE_URL) { $BASE_URL = "http://localhost:8080" }
$USERNAME_A = $env:USERNAME_A
if (-not $USERNAME_A) { $USERNAME_A = "demo_a" }
$USERNAME_B = $env:USERNAME_B
if (-not $USERNAME_B) { $USERNAME_B = "demo_b" }
$PASSWORD = $env:PASSWORD
if (-not $PASSWORD) { $PASSWORD = "CodeCommit123!" }

function Invoke-JsonPost($url, $payload, $token = $null) {
  $headers = @{ "Content-Type" = "application/json" }
  if ($token) { $headers["Authorization"] = "Bearer $token" }
  return Invoke-RestMethod -Method Post -Uri $url -Headers $headers -Body ($payload | ConvertTo-Json -Depth 5)
}

Write-Host "[1] Register A/B"
try { Invoke-JsonPost "$BASE_URL/v2/auth/register" @{ username = $USERNAME_A; password = $PASSWORD; stack = @("Python","Docker"); years_exp = 4; tabs_vs_spaces = $true; dark_mode = $true; puzzle_answer = "1" } | Out-Null } catch {}
try { Invoke-JsonPost "$BASE_URL/v2/auth/register" @{ username = $USERNAME_B; password = $PASSWORD; stack = @("TypeScript","React"); years_exp = 3; tabs_vs_spaces = $false; dark_mode = $true; puzzle_answer = "1" } | Out-Null } catch {}

Write-Host "[2] Login A/B"
$tokenA = (Invoke-JsonPost "$BASE_URL/v2/auth/login" @{ username = $USERNAME_A; password = $PASSWORD }).access_token
$tokenB = (Invoke-JsonPost "$BASE_URL/v2/auth/login" @{ username = $USERNAME_B; password = $PASSWORD }).access_token

$meA = Invoke-RestMethod -Method Get -Uri "$BASE_URL/v2/me" -Headers @{ Authorization = "Bearer $tokenA" }
$meB = Invoke-RestMethod -Method Get -Uri "$BASE_URL/v2/me" -Headers @{ Authorization = "Bearer $tokenB" }

Write-Host "[3] PR A -> B"
Invoke-JsonPost "$BASE_URL/v2/pull-requests" @{ to_user_id = $meB.id } $tokenA | Out-Null

Write-Host "[4] PR B -> A (auto-match)"
$match = Invoke-JsonPost "$BASE_URL/v2/pull-requests" @{ to_user_id = $meA.id } $tokenB
$chatId = $match.chat_id
Write-Host "CHAT_ID=$chatId"

Write-Host "[5] Mensaje chat"
Invoke-JsonPost "$BASE_URL/v2/chat/$chatId/messages" @{ body = "Hola demo comercial desde PowerShell" } $tokenA | Out-Null
$history = Invoke-RestMethod -Method Get -Uri "$BASE_URL/v2/chat/$chatId/messages" -Headers @{ Authorization = "Bearer $tokenA" }
$history | ConvertTo-Json -Depth 5

Write-Host "[6] Stress seed 100"
python -m src.codecommit.stress_seed --count 100

Write-Host "Demo PowerShell completada."

