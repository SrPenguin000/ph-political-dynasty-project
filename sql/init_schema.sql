-- PostgreSQL Data Warehouse Schema for Philippine Political Dynasty Analysis

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- 1. DIMENSION TABLES
-- ============================================================================
CREATE TABLE IF NOT EXISTS dim_geography (
    location_id SERIAL PRIMARY KEY,
    province_std VARCHAR(150) NOT NULL,
    town_std VARCHAR(150),
    region VARCHAR(100),
    is_city BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_geo_province_town UNIQUE NULLS NOT DISTINCT (province_std, town_std)
);

CREATE TABLE IF NOT EXISTS dim_person (
    person_id VARCHAR(100) PRIMARY KEY,
    first_name VARCHAR(150) NOT NULL,
    last_name VARCHAR(150) NOT NULL,
    middle_name VARCHAR(150),
    name_suffix VARCHAR(50),
    sex VARCHAR(20),
    sex_source VARCHAR(50),
    suffix_suspect BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dim_position (
    position_id SERIAL PRIMARY KEY,
    position_title VARCHAR(150) UNIQUE NOT NULL,
    governance_level VARCHAR(50) NOT NULL,
    term_length_years INT DEFAULT 3
);

-- ----------------------------------------------------------------------------
-- dim_clan: validated paternal-family groupings from 03_kinship_engine.ipynb
-- (clans.parquet). A clan only exists if 2+ people are linked by an actual
-- nuclear_family / father_son / paternal_kin edge -- NOT by surname text
-- matching. This is what tab_sim in the dashboard should group on.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_clan (
    clan_id VARCHAR(20) PRIMARY KEY,
    clan_surname VARCHAR(150),
    main_place VARCHAR(150),
    n_members INT NOT NULL,
    first_year INT,
    last_year INT,
    n_allied_clans INT DEFAULT 0
);

-- ============================================================================
-- 2. FACT TABLES
-- ============================================================================
CREATE TABLE IF NOT EXISTS fact_electoral_membership (
    membership_id VARCHAR(100) PRIMARY KEY,
    person_id VARCHAR(100) NOT NULL REFERENCES dim_person(person_id) ON DELETE CASCADE,
    location_id INT REFERENCES dim_geography(location_id),
    year INT NOT NULL,
    position VARCHAR(150) NOT NULL,
    party VARCHAR(150),
    source VARCHAR(50),
    locality_source VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_membership_person_year_pos UNIQUE (person_id, year, position)
);

CREATE TABLE IF NOT EXISTS fact_election_winner (
    winner_id SERIAL PRIMARY KEY,
    location_id INT REFERENCES dim_geography(location_id),
    year INT NOT NULL,
    position VARCHAR(150) NOT NULL,
    last_name VARCHAR(150) NOT NULL,
    first_name VARCHAR(150) NOT NULL,
    middle_name VARCHAR(150),
    party VARCHAR(150),
    is_national BOOLEAN DEFAULT FALSE,
    town_shift_suspect BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_winner_record UNIQUE (year, position, last_name, first_name, location_id)
);

CREATE TABLE IF NOT EXISTS fact_legislative_tenure (
    tenure_id SERIAL PRIMARY KEY,
    legislator_name VARCHAR(250) NOT NULL,
    first_name VARCHAR(150),
    middle_initial VARCHAR(10),
    name_suffix VARCHAR(50),
    location_id INT REFERENCES dim_geography(location_id),
    congress_number INT,
    period_std VARCHAR(100),
    start_year INT,
    end_year INT,
    is_party_list BOOLEAN DEFAULT FALSE,
    is_sectoral BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_legislator_tenure UNIQUE (legislator_name, congress_number, start_year, end_year)
);

CREATE TABLE IF NOT EXISTS fact_poverty_metric (
    poverty_id SERIAL PRIMARY KEY,
    location_id INT REFERENCES dim_geography(location_id),
    year INT NOT NULL,
    area_key VARCHAR(150) NOT NULL,
    level VARCHAR(50),
    poverty_incidence NUMERIC(6, 2) CHECK (poverty_incidence BETWEEN 0 AND 100),
    is_city BOOLEAN DEFAULT FALSE,
    is_combined_area BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_poverty_loc_year UNIQUE (location_id, year, area_key)
);

-- ----------------------------------------------------------------------------
-- fact_person_clan: one row per HF-sourced and Ateneo-sourced politician who 
-- belongs to a validated clan, from politicians.parquet (person_uid -> clan_id,
-- n_relatives). politicians.parquet spans HF + OpenHalalan + Roster + Ateneo
-- (person_uid). This table is loaded filtered to person_uid values prefixed 
-- "HF-" and "AT-", with that prefix stripped to recover the matching 
-- dim_person.person_id.
-- A person with no row here, or with clan_id NULL, has no validated
-- relative in the dataset -- NOT a dynasty, regardless of their surname.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_person_clan (
    person_id VARCHAR(100) PRIMARY KEY REFERENCES dim_person(person_id) ON DELETE CASCADE,
    clan_id VARCHAR(20) REFERENCES dim_clan(clan_id) ON DELETE SET NULL,
    n_relatives INT DEFAULT 0,
    has_relative_in_office BOOLEAN DEFAULT FALSE
);

-- For databases created before these columns existed (CREATE TABLE IF NOT EXISTS won't add them)
ALTER TABLE fact_electoral_membership ADD COLUMN IF NOT EXISTS party VARCHAR(150);
ALTER TABLE fact_electoral_membership ADD COLUMN IF NOT EXISTS source VARCHAR(50);

-- ============================================================================
-- 3. PERFORMANCE INDEXES
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_mem_person ON fact_electoral_membership(person_id);
CREATE INDEX IF NOT EXISTS idx_mem_year ON fact_electoral_membership(year);
CREATE INDEX IF NOT EXISTS idx_mem_location ON fact_electoral_membership(location_id);
CREATE INDEX IF NOT EXISTS idx_person_name ON dim_person(last_name, first_name);
CREATE INDEX IF NOT EXISTS idx_geo_province ON dim_geography(province_std);
CREATE INDEX IF NOT EXISTS idx_poverty_lookup ON fact_poverty_metric(year, location_id);
CREATE INDEX IF NOT EXISTS idx_person_clan_clan ON fact_person_clan(clan_id);