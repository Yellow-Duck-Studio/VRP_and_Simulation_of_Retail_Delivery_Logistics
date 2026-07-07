# Deployment & CI/CD Pipeline Documentation

## 1. Environment Setup

The application is deployed on an Ubuntu Virtual Machine located within a private network (behind a NAT, lacking a public IP). To overcome the network isolation and ensure automated deployments, the environment was configured using a pull-based architecture with a Self-Hosted Runner and an outbound tunnel.

### Virtual Machine Provisioning & Tooling
1. **Runtime & Containerization:** * Installed Docker Engine and Docker Compose plugin.
   * Added the current user to the `docker` group to allow execution without `sudo`.
   * Installed docker daemon on systemd (system startup).
2. **CI/CD Integration (GitHub Self-Hosted Runner):**
   * Registered a GitHub Self-Hosted Runner directly on the VM.
   * Added user to the runner service to allow it to run commands with necessary privileges. Added runner user to docker group for docker commands execution.
   * Configured the runner as a background systemd service (`sudo ./svc.sh install && sudo ./svc.sh start`). This allows the VM to poll GitHub for deployment jobs, bypassing the need for external inbound SSH access.
3. **Secrets & Environment Variables:**
   * Environment variables (like `PYTHONUNBUFFERED=1`) are managed directly within the `docker-compose.yml`. 
   * Additional sensitive secrets are stored in a `.env` file on the VM, which is securely ignored by Git.

---

## 2. CI/CD Pipeline Architecture

The pipeline is managed via GitHub Actions and is divided into two strict phases: Continuous Integration (cloud-based) and Continuous Deployment (on-premise).

**Workflow Trigger:** The pipeline triggers automatically on any `push` or `pull_request` to the `main` branch.

### Phase 1: Continuous Integration (CI)
* **Runner:** Executes on self-hosted infrastructure (`Ubuntu x64`).
* **Process:**
  1. Checks out the source code.
  2. Sets up Python 3.11 and Node.js 22.
  3. Installs dependencies for the Backend, Simulator, and Frontend.
  4. Runs full test suites (`pytest` for backend/simulator, `vitest` for frontend).
  5. Builds Docker images for the Backend, Frontend, and Simulator services and checks its states.
* **Gate:** If any test fails, the pipeline halts immediately, preventing broken code from reaching the deployment phase.

### Phase 2: Continuous Deployment (CD)
* **Runner:** Executes on the VM via the `self-hosted` runner.
* **Condition:** Only runs if the CI phase passes successfully AND the event is a push/merge to `main`.
* **Process:**
  1. The local runner pulls the latest verified code from the `main` branch.
  2. Executes `docker compose up -d --build`.
  3. In case of unexpected failure on VM side, rollback to previous working commit up docker containers and exit pipeline with error for notify.
  4. Docker reconstructs only the changed layers (Backend/Frontend/Simulator) and performs a rolling restart of the updated containers via the local Docker daemon.

---