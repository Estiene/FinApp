# Balance history and Early Pay (#10, #24)

This feature is developed on `feature/history-early-pay` from released main.
Migration `e8f901ab24cd` follows `d7e8f901ab23`.

## Behavior

- Accounts independently select Off, 1-day early, or 2-day early. Off is the
  migration default. Settings are managed on Accounts.
- Date mapping follows #24 exactly, including Monday -> prior Friday and
  Tuesday -> Monday for both Early Pay modes. Wednesday/Thursday/Friday move
  back one or two days; weekends move to Friday. The owner chose weekends
  only: bank holidays are not adjusted. Nominal income schedules are unchanged.
- Income is adjusted consistently in Cash Flow, Dashboard and new saved
  forecasts. Paydays just beyond the report end can appear in the preceding
  month/year. Separate deposits on the same adjusted date retain both amounts.
- Balance History records each successful actual-balance save. Corrections
  remain stored; charts show the latest observation for each effective date.
- Migration imports the one known dated balance per existing account, marked
  Imported with an unknown original entry time. No earlier data is invented.
- Save forecast explicitly captures today's Dashboard projected balance and
  the following 30, 90 or 180 days. Temporary report simulations are excluded.
  Opening a page never creates a forecast. No scheduler is required.
- Saved forecast amounts never change after bill, income, balance or Early Pay
  edits. Save a new forecast to compare changed assumptions. Capture times are UTC.
- Select an account and up to a 730-day window, then compare up to three saved
  forecasts. Actuals are individual observed points, not an interpolated daily
  balance. Tables expose exact values without requiring SVG hover interaction.
- All history is retained until the account is deleted; account deletion also
  deletes its history. No automatic retention or cleanup job is introduced.
  The comparison list shows at most the latest 100 captures overlapping the
  selected window. Narrow the window to find older captures.
- Downgrading this migration drops the new history and Early Pay settings.
  Keep a backup; do not use downgrade as a substitute for backup restoration.

## Isolated verification

Use the existing evaluation checkout and database, not the production checkout.
Preserve its local Compose port override to 5002. Back up the current evaluation
database before migrating. Fetch and check out `feature/history-early-pay`,
build the test web image, inspect `flask db current` and `flask db heads`, then
upgrade only the `finapp-stage5-test` project. Expected path:
`d7e8f901ab23 -> e8f901ab24cd`.

Manual checks, one at a time:

1. Existing accounts default to Early Pay Off; monthly Cash Flow totals remain
   unchanged. Review #4's existing per-account income, bill, card-payment and net totals.
2. Enable each Early Pay mode on a temporary receiving account and verify
   #24's weekday table, especially Monday, Tuesday, weekends and month/year edges.
3. Check another account remains Off and nominal income dates are unchanged.
4. Verify the Dashboard and Cash Flow agree on adjusted deposit dates.
5. Open Balance History. The existing dated actual balance is imported; earlier
   forecasts are explicitly unavailable.
6. Save a 30-day forecast. Check today's anchor matches the Dashboard and
   future amounts match the forward forecast rather than simulation balances.
7. Save another actual balance on a different effective date. Confirm both
   observations remain visible in History.
8. Change a future bill or income; confirm the previous saved forecast is unchanged.
9. Save a second forecast and compare the separate lines and exact-value tables.
10. Switch accounts and date ranges; verify observations and forecasts never
    leak into another account's chart. Check a range with missing history.

Automated checks run from `app/` using `python -m unittest discover -s tests -v`.
CI additionally checks PostgreSQL migration upgrade/downgrade and Chromium UI
flows. No merge or production upgrade is part of this development pass.
