#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"
USERNAME_A="${USERNAME_A:-demo_a}"
USERNAME_B="${USERNAME_B:-demo_b}"
PASSWORD="${PASSWORD:-CodeCommit123!}"

echo "[1] Register A"
curl -sS -X POST "$BASE_URL/v2/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$USERNAME_A\",\"password\":\"$PASSWORD\",\"stack\":[\"Python\",\"Docker\"],\"years_exp\":4,\"tabs_vs_spaces\":true,\"dark_mode\":true,\"puzzle_answer\":\"1\"}" || true
echo

echo "[2] Register B"
curl -sS -X POST "$BASE_URL/v2/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$USERNAME_B\",\"password\":\"$PASSWORD\",\"stack\":[\"TypeScript\",\"React\"],\"years_exp\":3,\"tabs_vs_spaces\":false,\"dark_mode\":true,\"puzzle_answer\":\"1\"}" || true
echo

echo "[3] Login A/B"
TOKEN_A=$(curl -sS -X POST "$BASE_URL/v2/auth/login" -H "Content-Type: application/json" -d "{\"username\":\"$USERNAME_A\",\"password\":\"$PASSWORD\"}" | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
TOKEN_B=$(curl -sS -X POST "$BASE_URL/v2/auth/login" -H "Content-Type: application/json" -d "{\"username\":\"$USERNAME_B\",\"password\":\"$PASSWORD\"}" | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
echo "TOKEN_A/TOKEN_B OK"

echo "[4] Obtener IDs"
ID_A=$(curl -sS "$BASE_URL/v2/me" -H "Authorization: Bearer $TOKEN_A" | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
ID_B=$(curl -sS "$BASE_URL/v2/me" -H "Authorization: Bearer $TOKEN_B" | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "A=$ID_A B=$ID_B"

echo "[5] PR A -> B"
curl -sS -X POST "$BASE_URL/v2/pull-requests" \
  -H "Authorization: Bearer $TOKEN_A" \
  -H "Content-Type: application/json" \
  -d "{\"to_user_id\":$ID_B}"
echo

echo "[6] PR B -> A (auto-match)"
MATCH_JSON=$(curl -sS -X POST "$BASE_URL/v2/pull-requests" \
  -H "Authorization: Bearer $TOKEN_B" \
  -H "Content-Type: application/json" \
  -d "{\"to_user_id\":$ID_A}")
echo "$MATCH_JSON"
CHAT_ID=$(echo "$MATCH_JSON" | python -c "import sys,json;print(json.load(sys.stdin).get('chat_id',''))")
echo "CHAT_ID=$CHAT_ID"

echo "[7] Mensaje chat"
curl -sS -X POST "$BASE_URL/v2/chat/$CHAT_ID/messages" \
  -H "Authorization: Bearer $TOKEN_A" \
  -H "Content-Type: application/json" \
  -d '{"body":"Hola demo comercial desde curl"}'
echo

echo "[8] Historial"
curl -sS "$BASE_URL/v2/chat/$CHAT_ID/messages" -H "Authorization: Bearer $TOKEN_A"
echo

echo "[9] Upload avatar (si existe ./sample-avatar.png)"
if [[ -f "./sample-avatar.png" ]]; then
  curl -sS -X POST "$BASE_URL/v2/me/avatar" \
    -H "Authorization: Bearer $TOKEN_A" \
    -F "image=@./sample-avatar.png"
  echo
else
  echo "No se encontró ./sample-avatar.png (paso opcional)."
fi

echo "[10] Stress seed (100 usuarios)"
python -m src.codecommit.stress_seed --count 100

echo "Demo curl completada."

