-- Stage 5A: payment scheduling settings.
-- PostgreSQL migration for existing FinApp databases.
-- Apply ONCE after backup, before deploying the Stage 5A application code.
-- This script is not automatically executed by Flask-Migrate.
ALTER TABLE credit_cards
    ADD COLUMN IF NOT EXISTS extra_payment_day INTEGER;
ALTER TABLE credit_cards
    ADD COLUMN IF NOT EXISTS bill_payment_timing VARCHAR(20) NOT NULL DEFAULT 'due_date';
ALTER TABLE credit_cards
    ADD COLUMN IF NOT EXISTS bill_payment_days_before INTEGER NOT NULL DEFAULT 0;

ALTER TABLE credit_cards
    ADD CONSTRAINT ck_card_extra_payment_day
    CHECK (extra_payment_day IS NULL OR extra_payment_day BETWEEN 1 AND 31);
ALTER TABLE credit_cards
    ADD CONSTRAINT ck_card_bill_payment_timing
    CHECK (bill_payment_timing IN ('due_date', 'days_before_due'));
ALTER TABLE credit_cards
    ADD CONSTRAINT ck_card_bill_days_before
    CHECK (bill_payment_days_before BETWEEN 0 AND 31);
