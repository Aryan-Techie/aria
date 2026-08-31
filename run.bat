@echo off
setlocal EnableDelayedExpansion
REM ===========================================================================
REM  Aria - one-command local startup (Windows)
REM
REM  Brings up: EspoCRM (Docker) -> backend -> cloudflared tunnel -> frontend,
REM  in that order, and writes the tunnel's new hostname into .env before the
REM  backend reads it. That ordering matters: the quick-tunnel URL changes on
REM  every restart, and settings are cached with lru_cache, so a backend
REM  started before the .env write serves calls on a dead URL and every Agora
REM  turn silently 404s.
REM
REM  Usage:  run.bat            start everything
REM          run.bat stop       stop everything (containers included)
REM ===========================================================================

cd /d "%~dp0"

if /i "%~1"=="stop" goto :stop

echo.
echo  ===============================================
echo    Aria - real-time voice AI sales agent
echo  ===============================================
echo.

REM A dev server left running from a previous session keeps port 3000/8000
REM and the new one silently serves a broken build - seen live as a 500 from
REM a page that had worked a minute earlier. Clear ours out first. Windows
REM are matched by title, so this only touches servers this script started.
taskkill /fi "WINDOWTITLE eq Aria backend*"  /t /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq Aria frontend*" /t /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq Aria tunnel*"   /t /f >nul 2>&1

REM ------------------------------------------------------------- preflight
echo  [1/7] Checking prerequisites...

set MISSING=0

where docker >nul 2>&1
if errorlevel 1 (
  echo        [X] Docker         NOT FOUND  - https://docs.docker.com/desktop/install/windows-install/
  set MISSING=1
) else (
  echo        [OK] Docker
)

where node >nul 2>&1
if errorlevel 1 (
  echo        [X] Node.js 18+    NOT FOUND  - https://nodejs.org/
  set MISSING=1
) else (
  echo        [OK] Node.js
)

where python >nul 2>&1
if errorlevel 1 (
  echo        [X] Python 3.11+   NOT FOUND  - https://www.python.org/downloads/
  set MISSING=1
) else (
  echo        [OK] Python
)

REM cloudflared exposes the local backend to Agora, which must reach it over
REM public HTTPS. Only needed for a real voice call - the test suite and the
REM CRM work without it.
where cloudflared >nul 2>&1
if errorlevel 1 (
  if exist "cloudflared.exe" (
    set CLOUDFLARED=cloudflared.exe
    echo        [OK] cloudflared ^(local copy^)
  ) else (
    echo        [X] cloudflared    NOT FOUND  - winget install --id Cloudflare.cloudflared
    set MISSING=1
  )
) else (
  set CLOUDFLARED=cloudflared
  echo        [OK] cloudflared
)

if "%MISSING%"=="1" (
  echo.
  echo  Install the items marked [X] above, then run this script again.
  echo.
  pause
  exit /b 1
)

REM ------------------------------------------------------------------ config
echo.
echo  [2/7] Checking configuration...

if not exist ".env" (
  echo        [X] .env not found.
  echo.
  echo        Copy backend\.env.example to .env in THIS folder and fill in:
  echo          AGORA_APP_ID, AGORA_APP_CERTIFICATE,
  echo          AGORA_CUSTOMER_KEY, AGORA_CUSTOMER_SECRET,
  echo          ANTHROPIC_API_KEY  ^(and GROQ_API_KEY for lower latency^),
  echo          LLM_SHARED_SECRET  ^(any long random string^)
  echo.
  echo        The .env at the REPO ROOT is the one that is read - not
  echo        backend\.env - and it is gitignored.
  echo.
  pause
  exit /b 1
)
echo        [OK] .env present

if not exist "backend\.venv\Scripts\python.exe" (
  echo        [..] Creating Python virtualenv ^(first run only^)...
  python -m venv backend\.venv
  backend\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
  backend\.venv\Scripts\python.exe -m pip install --quiet -r backend\requirements.txt
)
echo        [OK] Python virtualenv

if not exist "frontend\node_modules" (
  echo        [..] Installing frontend packages ^(first run only, takes a minute^)...
  pushd frontend && call npm install --silent && popd
)
echo        [OK] Frontend packages

REM --------------------------------------------------------------------- CRM
echo.
echo  [3/7] Starting EspoCRM ^(Docker^)...

docker info >nul 2>&1
if errorlevel 1 (
  echo        [..] Docker engine not running - launching Docker Desktop...
  start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
  echo        [..] Waiting for the engine ^(up to 3 minutes^)...
  for /l %%i in (1,1,36) do (
    call :sleep 5
    docker info >nul 2>&1
    if not errorlevel 1 goto :docker_ready
  )
  echo        [X] Docker engine did not start. Start Docker Desktop manually and retry.
  pause
  exit /b 1
)
:docker_ready
docker compose -f crm\docker-compose.yml up -d
if errorlevel 1 (
  echo        [X] Could not start the CRM containers.
  pause
  exit /b 1
)

REM First run pulls images AND self-installs the database, which takes far
REM longer than the container simply being up. Poll the API rather than
REM guessing with a fixed sleep.
echo        [..] Waiting for EspoCRM to answer ^(first run installs the DB, ~2 min^)...
for /l %%i in (1,1,60) do (
  curl -s -o nul -m 5 http://localhost:8080/ && goto :crm_ready
  call :sleep 5
)
echo        [!] EspoCRM did not answer in time. Continuing - the backend will
echo            fall back to its in-memory CRM store, so the call still works.
goto :crm_done
:crm_ready
echo        [OK] EspoCRM up at http://localhost:8080  ^(admin / aria-demo-admin^)
:crm_done

REM ------------------------------------------------------------ provisioning
echo.
echo  [4/7] Provisioning CRM ^(role, fields, layout - idempotent^)...
findstr /b /c:"ESPOCRM_API_KEY=" .env | findstr /v /c:"ESPOCRM_API_KEY=$" >nul 2>&1
if errorlevel 1 (
  echo        [!] ESPOCRM_API_KEY is not set in .env.
  echo            Run:  python scripts\provision_crm.py
  echo            then paste the printed lines into .env and re-run this script.
) else (
  python scripts\provision_crm.py
)

REM ----------------------------------------------------------------- backend
echo.
echo  [5/7] Starting backend on :8000...
start "Aria backend" /min cmd /c "cd /d "%~dp0backend" && .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"

for /l %%i in (1,1,30) do (
  curl -s -o nul -m 3 http://localhost:8000/healthz && goto :backend_ready
  call :sleep 2
)
echo        [X] Backend did not come up. Check the "Aria backend" window.
pause
exit /b 1
:backend_ready
echo        [OK] Backend healthy

REM ------------------------------------------------------------------ tunnel
echo.
echo  [6/7] Starting tunnel and updating PUBLIC_BASE_URL...
if exist "%TEMP%\aria-tunnel.log" del "%TEMP%\aria-tunnel.log"
start "Aria tunnel" /min cmd /c "%CLOUDFLARED% tunnel --url http://localhost:8000 > "%TEMP%\aria-tunnel.log" 2>&1"

REM cloudflared prints the assigned hostname into its log a second or two
REM after start. Poll for it rather than sleeping a fixed amount.
set TUNNEL_URL=
for /l %%i in (1,1,30) do (
  if not defined TUNNEL_URL (
    call :sleep 2
    for /f "usebackq tokens=*" %%u in (`powershell -NoProfile -Command "$m = Select-String -Path '%TEMP%\aria-tunnel.log' -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -AllMatches -ErrorAction SilentlyContinue | Select-Object -First 1; if ($m) { $m.Matches[0].Value }"`) do set TUNNEL_URL=%%u
  )
)

if not defined TUNNEL_URL goto :no_tunnel

echo        [OK] Tunnel: !TUNNEL_URL!
REM Write the new hostname, THEN restart the backend: settings are cached
REM with lru_cache, so a running backend keeps serving the old (dead) URL.
python scripts\set_tunnel_url.py "!TUNNEL_URL!"
echo        [..] Restarting backend so it reads the new URL...
taskkill /fi "WINDOWTITLE eq Aria backend*" /t /f >nul 2>&1
call :sleep 2
start "Aria backend" /min cmd /c "cd /d "%~dp0backend" && .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"
for /l %%i in (1,1,30) do (
  curl -s -o nul -m 3 http://localhost:8000/healthz && goto :backend_restarted
  call :sleep 2
)
:backend_restarted
echo        [OK] Backend restarted with the live tunnel URL
goto :tunnel_done

:no_tunnel
echo        [!] Could not read the tunnel URL. Voice calls will fail until
echo            PUBLIC_BASE_URL in .env is set by hand and the backend restarted.

:tunnel_done

REM ---------------------------------------------------------------- frontend
echo.
echo  [7/7] Starting frontend on :3000...
start "Aria frontend" /min cmd /c "cd /d "%~dp0frontend" && npm run dev"

for /l %%i in (1,1,45) do (
  curl -s -o nul -m 3 http://localhost:3000 && goto :frontend_ready
  call :sleep 2
)
echo        [!] Frontend slow to start - check the "Aria frontend" window.
:frontend_ready
echo        [OK] Frontend up

REM ------------------------------------------------------------------- ready
echo.
echo  ===============================================
echo    Ready
echo  ===============================================
echo.
echo    Console : http://localhost:3000     ^<- talk to Aria here
echo    CRM     : http://localhost:8080     ^<- admin / aria-demo-admin
echo.
echo    Open a Lead in the CRM beside the console. It updates itself
echo    while Aria talks - no refresh needed.
echo.
echo    Mic: pick "Microphone Array", NOT the device labelled
echo    "Realtek HIGH Definition" ^(that one is a silent virtual cable^).
echo.
echo    Stop everything:  run.bat stop
echo.

start "" http://localhost:3000
start "" http://localhost:8080

echo  Press any key to close this window ^(services keep running^)...
pause >nul
exit /b 0

REM ======================================================================
REM  `timeout` refuses to run when stdin is redirected ("Input redirection is
REM  not supported"), which happens whenever this script is piped or launched
REM  from another tool. ping against loopback is the portable equivalent.
:sleep
set /a _s=%~1+1
ping -n %_s% 127.0.0.1 >nul 2>&1
exit /b 0

REM ======================================================================
:stop
echo.
echo  Stopping Aria...
taskkill /fi "WINDOWTITLE eq Aria backend*"  /t /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq Aria frontend*" /t /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq Aria tunnel*"   /t /f >nul 2>&1
echo    [OK] Backend, frontend and tunnel stopped
docker compose -f crm\docker-compose.yml stop >nul 2>&1
echo    [OK] CRM containers stopped ^(data kept - "up" restores it^)
echo.
exit /b 0
