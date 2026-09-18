# Verification — How to Know the Platform Works

Run these in order. Each one tests one level of the stack. Do not
proceed to the next level until the current one passes.

## Level 1 — All containers running

    cd ~/nettrades-platform/deploy/docker
    docker compose ps

Expect: 15 containers, all `Up`, most `(healthy)`.

Failures:
- `odoo` not Up → check `docker compose logs odoo`
- `langgraph-server` not healthy → check `docker compose logs langgraph-server`
- `postgres` not healthy → check `docker compose logs postgres`

## Level 2 — Odoo responds

    curl http://localhost:8069/web/health

Expect: HTTP 200.

## Level 3 — LangGraph responds

    curl http://localhost:8000/health

Expect: `{"status":"ok","service":"langgraph"}`.

## Level 4 — All modules installed

    cd ~/nettrades-platform/deploy/docker
    docker compose exec -T postgres psql -U odoo -d odoo -c \
      "SELECT name, state FROM ir_module_module
       WHERE name LIKE 'nettrades_%' ORDER BY name;"

Expect: every NETTRADES module shows `state = installed`.

Alternate: open the Launcher → **Modules** tab. Every module should be
green (Installed).

## Level 5 — Admin UI is reachable

Open http://localhost:8069 in a browser. Log in as `admin`. You should
see the **NETTRADES** app in the app switcher. Clicking it should show
the sub-menus: Users, Companies, Projects, Fields, Reviews, Experience,
Fairness, Ask Someone, Good Answer, etc.

## Level 6 — Chat works end-to-end

Open http://localhost:3002 in a browser. Send `hello`. You should get
a response within 30 seconds.

If the response is slow or fails:
- Check the LangGraph log: `docker compose logs --tail=50 langgraph-server`
- Check the inference backend: `docker compose logs --tail=20 dynamo` (or `llama-cpp`)

## Level 7 — Tool calls reach Odoo

In the chat, send:

    create a project called "Verification Test" with a budget of 1000

Expect: LangGraph calls `create_project` via the gateway. Odoo creates
a `nettrades.project` record.

Verify:

    docker compose exec -T postgres psql -U odoo -d odoo -c \
      "SELECT id, title, budget FROM nettrades_project ORDER BY id DESC LIMIT 5;"

Expect: the newly created project appears.

## Level 8 — Tenant isolation

(This requires two test users in different companies. Create them if
they don't exist.)

Log in as User A (Company A). Create a project. Log in as User B
(Company B). Search for projects. User B should NOT see User A's
project.

## Level 9 — Spoke failure recovery

(Requires a working RPC cluster with at least 2 spokes.)

1. Start a conversation in the AI Chat UI. Send several messages so
   the thread has history.
2. In another terminal, stop one spoke's `rpc-server`.
3. Send the next message.

Expect:
- An error message in the chat: *"Cluster interrupted. Retry."*
- The conversation history is intact.
- The next message after retry succeeds (with the recomputed cluster).

## Level 10 — Persistence across restart

1. Complete a conversation.
2. `docker compose stop odoo langgraph-server`
3. `docker compose up -d odoo langgraph-server`
4. Reload the chat. Send a follow-up message to the same thread.

Expect: the reply reflects the earlier conversation. This proves the
checkpointer works.

## Level 11 — Launcher build

    cd ~/nettrades-platform/installer
    npm install
    npm run build:linux
    npm start

Expect: the Electron window opens with the NETTRADES dashboard.

## Level 12 — Full deployment from scratch

(Do this on a fresh VM. It's the ultimate test.)

    git clone -b dev-deployment1 https://github.com/nettrades/nettrades-platform.git
    cd nettrades-platform
    chmod +x scripts/*.sh scripts/lib/*.sh
    ./scripts/nettrades-setup.sh all --force

Expect: the installer completes with `ALL MODULES INSTALLED SUCCESSFULLY`.

This is the acceptance test. If it passes on a fresh VM, the platform
is deployable.