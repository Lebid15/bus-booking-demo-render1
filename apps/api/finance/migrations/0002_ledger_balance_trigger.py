from django.db import migrations


CREATE_FUNCTION = r"""
CREATE OR REPLACE FUNCTION enforce_ledger_entry_balance() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    target uuid;
    debit_total numeric(18,2);
    credit_total numeric(18,2);
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        target := OLD.entry_id;
        SELECT
            COALESCE(SUM(CASE WHEN direction='D' THEN amount ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN direction='C' THEN amount ELSE 0 END), 0)
        INTO debit_total, credit_total
        FROM ledger_postings
        WHERE entry_id=target;
        IF debit_total <= 0 OR debit_total <> credit_total THEN
            RAISE EXCEPTION USING
                ERRCODE = '23514',
                MESSAGE = 'ledger entry ' || target || ' is unbalanced: debit ' || debit_total || ', credit ' || credit_total;
        END IF;
    END IF;

    IF TG_OP = 'INSERT' OR (TG_OP = 'UPDATE' AND NEW.entry_id IS DISTINCT FROM OLD.entry_id) THEN
        target := NEW.entry_id;
        SELECT
            COALESCE(SUM(CASE WHEN direction='D' THEN amount ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN direction='C' THEN amount ELSE 0 END), 0)
        INTO debit_total, credit_total
        FROM ledger_postings
        WHERE entry_id=target;
        IF debit_total <= 0 OR debit_total <> credit_total THEN
            RAISE EXCEPTION USING
                ERRCODE = '23514',
                MESSAGE = 'ledger entry ' || target || ' is unbalanced: debit ' || debit_total || ', credit ' || credit_total;
        END IF;
    END IF;
    RETURN NULL;
END;
$$;
"""

CREATE_TRIGGER = r"""
CREATE CONSTRAINT TRIGGER trg_ledger_balance
AFTER INSERT OR UPDATE OR DELETE ON ledger_postings
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION enforce_ledger_entry_balance();
"""

DROP_SQL = r"""
DROP TRIGGER IF EXISTS trg_ledger_balance ON ledger_postings;
DROP FUNCTION IF EXISTS enforce_ledger_entry_balance();
"""


def create_trigger(apps, schema_editor):  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(CREATE_FUNCTION)
    schema_editor.execute(CREATE_TRIGGER)


def drop_trigger(apps, schema_editor):  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(DROP_SQL)


class Migration(migrations.Migration):
    dependencies = [("finance", "0001_initial")]
    operations = [migrations.RunPython(create_trigger, drop_trigger)]
