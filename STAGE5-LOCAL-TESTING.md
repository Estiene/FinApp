# Stage 5C/5D isolated local evaluation

**Do not run this against the existing FinApp Docker Compose project or database.** The test stack uses its own Compose project, named database volume, and localhost-only port 5001. It does not use the production nginx service or ports 80/443/5000.

## 1. Get the branch into a separate WSL folder

Open Ubuntu in WSL, then:

```bash
cd ~/repos
git clone --branch feature/stage-5c-5d-forecasting-dashboard --single-branch https://github.com/Estiene/FinApp.git finapp-stage5-evaluation
cd finapp-stage5-evaluation
```

If the folder already exists, do not clone over it. Use `git status` and `git pull --ff-only` inside that test folder instead.

## 2. Start the isolated database and application

```bash
docker compose -p finapp-stage5-test -f docker-compose.stage5-test.yml up -d --build
docker compose -p finapp-stage5-test -f docker-compose.stage5-test.yml ps
```

The app will be reachable at **http://127.0.0.1:5001** after its database is prepared. The database starts empty; the application will not be usable until you restore a compatible copy of your existing database or initialize a supported baseline. **Do not run historical migrations on an empty database:** the project's earliest migration expects pre-existing tables.

## 3. Populate with a COPY of existing data (recommended)

First, ensure your existing production database backup is current. Keep it in a private local folder. To make a new custom-format dump from the existing production database, run:

```bash
docker exec finapp-db-1 pg_dump -U finapp -d finapp -Fc > ~/finapp-stage5-copy.dump
```

This command only reads the production database. It writes the dump to a WSL file, **not** into the production container. Never commit this dump to Git.

Restore the copy into the isolated test database:

```bash
docker compose -p finapp-stage5-test -f docker-compose.stage5-test.yml exec -T db pg_restore -U finapp -d finapp --no-owner --no-privileges < ~/finapp-stage5-copy.dump
```

The restore target is explicitly the **finapp-stage5-test** Compose project. If the restore reports errors, stop and review them rather than proceeding with migrations.

## 4. Upgrade the COPY and inspect the app

```bash
docker compose -p finapp-stage5-test -f docker-compose.stage5-test.yml exec web flask db current
docker compose -p finapp-stage5-test -f docker-compose.stage5-test.yml exec web flask db upgrade
docker compose -p finapp-stage5-test -f docker-compose.stage5-test.yml exec web flask db current
```

If the restored database is already at the current migration head, upgrade may have nothing to do. If it has an unexpected revision, **stop** and ask for help; do not stamp or reset the database.

Open http://127.0.0.1:5001 and check:
- Dashboard bank balances and the next-30-days forecast, including the first negative-balance warning.
- Credit-card utilization, APR, promotional expiry and payoff estimate wording.
- Statement reminders: overdue, upcoming, stale and completed payments.
- Credit-card editing and deactivation restrictions.
- Cash-flow report planned payments, including bills paid by card.

The copy contains your actual financial data. The test app binds only to your computer's loopback interface, but treat the dump and test database as private.

## 5. Shut down safely

```bash
docker compose -p finapp-stage5-test -f docker-compose.stage5-test.yml down
```

This retains the isolated test database for another session. To permanently delete **only** the isolated test database volume, run `docker compose -p finapp-stage5-test -f docker-compose.stage5-test.yml down -v` after verifying the project name. Never run `down -v` against the production Compose project.

**Safety note:** These commands are prepared for review, not yet executed on your Windows/WSL computer. The branch is not merged or deployed.
