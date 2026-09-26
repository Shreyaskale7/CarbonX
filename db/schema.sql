-- CarbonX schema. PostgreSQL 16.
--
-- Two temporal axes throughout:
--   valid_time       when the fact was true in the world
--   transaction_time when this system learned it  (system_time_range)
--
-- Nothing is ever UPDATEd in place on a temporal table. Rows are closed
-- (system_time_range upper bound set) and a new row inserted. This is what
-- makes `AS OF` queries — and therefore invariant 1 — possible.

CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- 1. ORGANISATION / FACILITY
-- ============================================================

CREATE TABLE organisation (
    org_id          BIGSERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    cin             TEXT,
    ccts_sector     TEXT,          -- aluminium | cement | chlor_alkali | fertiliser
                                   -- | iron_steel | pulp_paper | petrochemicals
                                   -- | petroleum_refinery | textile | NULL
    is_obligated    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE facility (
    facility_id     BIGSERIAL PRIMARY KEY,
    org_id          BIGINT NOT NULL REFERENCES organisation(org_id),
    name            TEXT NOT NULL,
    state           TEXT NOT NULL,
    grid_region     TEXT,          -- CEA regional grid, for regional factors
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- 2. EMISSION FACTOR REGISTRY  (the heart of the project)
-- ============================================================

-- A published source document: "CEA CO2 Baseline Database v21.0"
CREATE TABLE factor_source (
    source_id       BIGSERIAL PRIMARY KEY,
    publisher       TEXT NOT NULL,          -- CEA | IPCC | GHG_PROTOCOL
    dataset_name    TEXT NOT NULL,          -- 'CO2 Baseline Database'
    version_label   TEXT NOT NULL,          -- 'v21.0'
    version_ordinal INT  NOT NULL,          -- 21  (for ordering; labels are messy)
    published_on    DATE,
    covers_fy       TEXT,                   -- 'FY2024-25'
    source_url      TEXT NOT NULL,
    file_sha256     CHAR(64),               -- hash of the downloaded artefact
    retrieved_at    TIMESTAMPTZ,
    UNIQUE (publisher, dataset_name, version_ordinal)
);

-- One factor value. Bitemporal.
CREATE TABLE emission_factor (
    factor_id       BIGSERIAL PRIMARY KEY,
    source_id       BIGINT NOT NULL REFERENCES factor_source(source_id),
    factor_key      TEXT NOT NULL,          -- 'grid.IN.combined_margin'
                                            -- 'fuel.diesel.stationary'
    value           NUMERIC(18,9) NOT NULL,
    numerator_unit  TEXT NOT NULL,          -- 'tCO2e'
    denominator_unit TEXT NOT NULL,         -- 'MWh' | 'litre' | 'sm3'
    geography       TEXT NOT NULL DEFAULT 'IN',
    margin_type     TEXT,                   -- OM | BM | CM | weighted_avg | NULL
    -- uncertainty, from IPCC published ranges. NULL where none is published.
    uncertainty_low  NUMERIC(18,9),
    uncertainty_high NUMERIC(18,9),
    uncertainty_basis TEXT,                 -- 'IPCC 2006 Vol2 Table 2.2' etc

    valid_time       DATERANGE NOT NULL,    -- the FY this factor describes
    system_time_range TSTZRANGE NOT NULL DEFAULT tstzrange(now(), NULL),
    supersedes       BIGINT REFERENCES emission_factor(factor_id),

    -- No two rows may claim the same factor_key + geography for overlapping
    -- valid AND system time. This is the DB enforcing that history is coherent.
    EXCLUDE USING gist (
        factor_key WITH =,
        geography  WITH =,
        valid_time WITH &&,
        system_time_range WITH &&
    )
);

CREATE INDEX ix_factor_key_valid ON emission_factor
    USING gist (factor_key, valid_time, system_time_range);

-- ============================================================
-- 3. RESOLUTION POLICY  (RQ3 lives here)
-- ============================================================
-- Given a compliance year, a report date and available factor versions,
-- WHICH factor applies? BEE may not specify. We encode competing policies
-- and show they produce different compliance outcomes on identical data.

CREATE TABLE resolution_policy (
    policy_id       BIGSERIAL PRIMARY KEY,
    code            TEXT UNIQUE NOT NULL,
    -- LATEST_AVAILABLE    newest version published before report date
    -- VINTAGE_MATCHED     version whose covers_fy == compliance year
    -- AS_OF_REPORT        version current at report submission
    -- BASELINE_FROZEN     the version used to set the entity's baseline
    description     TEXT NOT NULL,
    is_default      BOOLEAN NOT NULL DEFAULT FALSE
);

-- ============================================================
-- 4. PRODUCTION BASIS  (the denominator — versioned too)
-- ============================================================
-- GEI is emissions / production. The denominator is as contestable as the
-- numerator: product definitions, co-product allocation, boundary. Most
-- implementations version factors and forget this. We don't.

CREATE TABLE production_basis (
    basis_id        BIGSERIAL PRIMARY KEY,
    facility_id     BIGINT NOT NULL REFERENCES facility(facility_id),
    product_code    TEXT NOT NULL,
    unit            TEXT NOT NULL,          -- 'tonne'
    allocation_rule TEXT NOT NULL,          -- 'mass' | 'economic' | 'none'
    boundary_note   TEXT,                   -- what is inside the gate
    valid_time      DATERANGE NOT NULL,
    system_time_range TSTZRANGE NOT NULL DEFAULT tstzrange(now(), NULL),
    EXCLUDE USING gist (
        facility_id WITH =, product_code WITH =,
        valid_time WITH &&, system_time_range WITH &&
    )
);

CREATE TABLE production_record (
    production_id   BIGSERIAL PRIMARY KEY,
    basis_id        BIGINT NOT NULL REFERENCES production_basis(basis_id),
    period          DATERANGE NOT NULL,
    quantity        NUMERIC(18,6) NOT NULL,
    unit            TEXT NOT NULL,
    document_id     BIGINT,                 -- FK added after source_document
    system_time_range TSTZRANGE NOT NULL DEFAULT tstzrange(now(), NULL)
);

-- ============================================================
-- 5. EVIDENCE
-- ============================================================

CREATE TABLE source_document (
    document_id     BIGSERIAL PRIMARY KEY,
    facility_id     BIGINT REFERENCES facility(facility_id),
    doc_type        TEXT NOT NULL,          -- electricity_bill | fuel_invoice
                                            -- | meter_reading | production_log
    filename        TEXT NOT NULL,
    storage_path    TEXT NOT NULL,
    sha256          CHAR(64) NOT NULL,
    mime_type       TEXT,
    issuer          TEXT,                   -- 'BESCOM' | 'JVVNL' | ...
    uploaded_by     BIGINT,
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    redacted        BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (sha256)                          -- same file uploaded twice = same row
);

ALTER TABLE production_record
    ADD CONSTRAINT fk_prod_doc FOREIGN KEY (document_id)
    REFERENCES source_document(document_id);

-- What the extraction model read out of a document, with calibrated confidence.
CREATE TABLE extraction_result (
    extraction_id   BIGSERIAL PRIMARY KEY,
    document_id     BIGINT NOT NULL REFERENCES source_document(document_id),
    field_name      TEXT NOT NULL,          -- consumption_kwh | period_start
                                            -- | meter_id | tariff | issuer
    raw_value       TEXT,
    parsed_value    NUMERIC(18,6),
    unit            TEXT,
    confidence      NUMERIC(5,4),           -- CALIBRATED, not raw softmax
    model_version   TEXT NOT NULL,
    human_verified  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- 6. ACTIVITY DATA
-- ============================================================

CREATE TABLE activity (
    activity_id     BIGSERIAL PRIMARY KEY,
    facility_id     BIGINT NOT NULL REFERENCES facility(facility_id),
    activity_type   TEXT NOT NULL,          -- grid_electricity | diesel
                                            -- | natural_gas | coal
    scope           SMALLINT NOT NULL CHECK (scope IN (1,2)),
    period          DATERANGE NOT NULL,
    quantity        NUMERIC(18,6) NOT NULL,
    unit            TEXT NOT NULL,
    document_id     BIGINT REFERENCES source_document(document_id),
    extraction_id   BIGINT REFERENCES extraction_result(extraction_id),
    entered_by      BIGINT,
    system_time_range TSTZRANGE NOT NULL DEFAULT tstzrange(now(), NULL),
    EXCLUDE USING gist (
        facility_id WITH =, activity_type WITH =,
        period WITH &&, system_time_range WITH &&
    )
);

-- ============================================================
-- 7. CALCULATION  (pins everything it used, forever)
-- ============================================================

CREATE TABLE calculation (
    calculation_id  BIGSERIAL PRIMARY KEY,
    activity_id     BIGINT NOT NULL REFERENCES activity(activity_id),
    factor_id       BIGINT NOT NULL REFERENCES emission_factor(factor_id),
    policy_id       BIGINT NOT NULL REFERENCES resolution_policy(policy_id),
    engine_version  TEXT NOT NULL,          -- semver of the calc engine
    result_value    NUMERIC(18,6) NOT NULL,
    result_unit     TEXT NOT NULL,          -- always tCO2e
    -- propagated uncertainty, where an empirical basis exists
    result_low      NUMERIC(18,6),
    result_high     NUMERIC(18,6),
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_by   BIGINT REFERENCES calculation(calculation_id)
);

CREATE INDEX ix_calc_activity ON calculation(activity_id);

CREATE TABLE ledger_entry (
    entry_id        BIGSERIAL PRIMARY KEY,
    calculation_id  BIGINT NOT NULL REFERENCES calculation(calculation_id),
    facility_id     BIGINT NOT NULL REFERENCES facility(facility_id),
    scope           SMALLINT NOT NULL,
    period          DATERANGE NOT NULL,
    tco2e           NUMERIC(18,6) NOT NULL,
    system_time_range TSTZRANGE NOT NULL DEFAULT tstzrange(now(), NULL)
);

-- ============================================================
-- 8. REPORT  (an immutable snapshot — the reproducibility unit)
-- ============================================================

CREATE TABLE report (
    report_id       BIGSERIAL PRIMARY KEY,
    org_id          BIGINT NOT NULL REFERENCES organisation(org_id),
    compliance_year TEXT NOT NULL,          -- 'FY2025-26'
    policy_id       BIGINT NOT NULL REFERENCES resolution_policy(policy_id),
    as_of           TIMESTAMPTZ NOT NULL,   -- the transaction time it reads
    total_tco2e     NUMERIC(18,6) NOT NULL,
    production_qty  NUMERIC(18,6),
    gei             NUMERIC(18,9),          -- tCO2e per unit product
    output_sha256   CHAR(64) NOT NULL,      -- hash of canonical JSON output
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- 9. AUDIT TRAIL  (hash-chained, trigger-enforced)
-- ============================================================

CREATE TABLE audit_event (
    event_id        BIGSERIAL PRIMARY KEY,
    entity_table    TEXT NOT NULL,
    entity_id       BIGINT NOT NULL,
    action          TEXT NOT NULL,          -- INSERT | UPDATE | DELETE
    old_value       JSONB,
    new_value       JSONB,
    actor           TEXT,
    reason          TEXT,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    prev_hash       CHAR(64),
    event_hash      CHAR(64) NOT NULL
);

CREATE INDEX ix_audit_entity ON audit_event(entity_table, entity_id);

-- Hash chain: each event includes the previous event's hash. Tampering with
-- history breaks the chain and is detectable. This is tamper-EVIDENCE.
-- It is NOT a blockchain and must never be described as one: we need
-- detectability, not distributed consensus.
CREATE OR REPLACE FUNCTION fn_audit() RETURNS TRIGGER AS $$
DECLARE
    v_prev CHAR(64);
    v_old  JSONB;
    v_new  JSONB;
    v_payload TEXT;
BEGIN
    SELECT event_hash INTO v_prev FROM audit_event ORDER BY event_id DESC LIMIT 1;

    IF TG_OP = 'DELETE' THEN
        v_old := to_jsonb(OLD); v_new := NULL;
    ELSIF TG_OP = 'INSERT' THEN
        v_old := NULL;          v_new := to_jsonb(NEW);
    ELSE
        v_old := to_jsonb(OLD); v_new := to_jsonb(NEW);
    END IF;

    v_payload := coalesce(v_prev,'') || TG_TABLE_NAME || TG_OP
                 || coalesce(v_old::text,'') || coalesce(v_new::text,'')
                 || now()::text;

    INSERT INTO audit_event(entity_table, entity_id, action, old_value,
                            new_value, actor, prev_hash, event_hash)
    VALUES (
        TG_TABLE_NAME,
        coalesce((v_new->>'activity_id')::bigint,
                 (v_old->>'activity_id')::bigint,
                 (v_new->>'factor_id')::bigint,
                 (v_old->>'factor_id')::bigint, 0),
        TG_OP, v_old, v_new,
        current_setting('carbonx.actor', TRUE),
        v_prev,
        encode(digest(v_payload, 'sha256'), 'hex')
    );
    RETURN COALESCE(NEW, OLD);
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER tg_audit_activity
    AFTER INSERT OR UPDATE OR DELETE ON activity
    FOR EACH ROW EXECUTE FUNCTION fn_audit();

CREATE TRIGGER tg_audit_factor
    AFTER INSERT OR UPDATE OR DELETE ON emission_factor
    FOR EACH ROW EXECUTE FUNCTION fn_audit();

CREATE TRIGGER tg_audit_production
    AFTER INSERT OR UPDATE OR DELETE ON production_record
    FOR EACH ROW EXECUTE FUNCTION fn_audit();

-- ============================================================
-- 10. MATERIALITY  (GHG Protocol / SBTi 5% threshold)
-- ============================================================

CREATE TABLE materiality_assessment (
    assessment_id   BIGSERIAL PRIMARY KEY,
    org_id          BIGINT NOT NULL REFERENCES organisation(org_id),
    trigger_type    TEXT NOT NULL,          -- factor_supersession | boundary_change
                                            -- | data_correction | allocation_change
    trigger_ref     BIGINT,
    baseline_year   TEXT NOT NULL,
    before_tco2e    NUMERIC(18,6) NOT NULL,
    after_tco2e     NUMERIC(18,6) NOT NULL,
    pct_change      NUMERIC(8,4) NOT NULL,
    threshold_pct   NUMERIC(8,4) NOT NULL DEFAULT 5.0,
    requires_recalc BOOLEAN NOT NULL,
    disclosure_text TEXT,                   -- auto-drafted
    assessed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- 11. CREDIT LIFECYCLE  (ToC — automaton, no trading)
-- ============================================================

CREATE TABLE credit (
    credit_id       BIGSERIAL PRIMARY KEY,
    org_id          BIGINT NOT NULL REFERENCES organisation(org_id),
    vintage_year    TEXT NOT NULL,
    quantity_tco2e  NUMERIC(18,6) NOT NULL CHECK (quantity_tco2e > 0),
    state           TEXT NOT NULL,          -- ISSUED | HELD | SURRENDERED | RETIRED
    report_id       BIGINT REFERENCES report(report_id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE credit_transition (
    transition_id   BIGSERIAL PRIMARY KEY,
    credit_id       BIGINT NOT NULL REFERENCES credit(credit_id),
    from_state      TEXT,
    to_state        TEXT NOT NULL,
    symbol          TEXT NOT NULL,          -- issue | hold | surrender | retire
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Safety properties we PROVE by reachability enumeration (not just test):
--   P1  no reachable path re-surrenders a RETIRED credit
--   P2  no credit is simultaneously held by two orgs
--   P3  conservation: sum(issued) = sum(held) + sum(surrendered) + sum(retired)

-- ============================================================
-- 12. AUDIT SAMPLING  (AI/ML — learning to rank)
-- ============================================================

CREATE TABLE sampling_run (
    run_id          BIGSERIAL PRIMARY KEY,
    report_id       BIGINT NOT NULL REFERENCES report(report_id),
    budget_pct      NUMERIC(5,2) NOT NULL,
    strategy        TEXT NOT NULL,          -- random | value_weighted | learned
    model_version   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sampling_selection (
    selection_id    BIGSERIAL PRIMARY KEY,
    run_id          BIGINT NOT NULL REFERENCES sampling_run(run_id),
    activity_id     BIGINT NOT NULL REFERENCES activity(activity_id),
    rank            INT NOT NULL,
    risk_score      NUMERIC(8,6) NOT NULL,
    error_found     BOOLEAN                 -- filled in after verification
);

-- ============================================================
-- 13. MATERIALISED VIEWS
-- ============================================================

CREATE MATERIALIZED VIEW mv_facility_period_emissions AS
SELECT l.facility_id, l.scope, lower(l.period) AS period_start,
       sum(l.tco2e) AS tco2e
FROM ledger_entry l
WHERE upper_inf(l.system_time_range)
GROUP BY 1,2,3;

CREATE MATERIALIZED VIEW mv_audit_coverage AS
-- fraction of reported tCO2e whose lineage terminates in a hashed document.
-- The single number a verifier wants and nobody publishes.
SELECT f.facility_id,
       sum(c.result_value) FILTER (WHERE d.sha256 IS NOT NULL) AS traced_tco2e,
       sum(c.result_value)                                     AS total_tco2e,
       CASE WHEN sum(c.result_value) = 0 THEN NULL
            ELSE round(100 * sum(c.result_value)
                 FILTER (WHERE d.sha256 IS NOT NULL) / sum(c.result_value), 2)
       END AS coverage_pct
FROM calculation c
JOIN activity a  ON a.activity_id = c.activity_id
JOIN facility f  ON f.facility_id = a.facility_id
LEFT JOIN source_document d ON d.document_id = a.document_id
WHERE c.superseded_by IS NULL
GROUP BY f.facility_id;
