# e2e

`login_e2e.sh` builds `admin-ui` (nginx) and `niyan-api` in an isolated compose
project (`niyan-login-e2e`, UI on 127.0.0.1:13080) and checks
`POST /api/auth/login` through the nginx `/api` proxy: right creds → 200,
wrong → 401, 6th failure within 60 s → 429 with `Retry-After`. It removes only
its own containers, volumes and images. Override with `E2E_PROJECT`,
`E2E_UI_PORT`. Runs in CI via `.github/workflows/login-e2e.yml`.
