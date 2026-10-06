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

-- ============================================================================
-- 2. FACT TABLES
-- ============================================================================
CREATE TABLE IF NOT EXISTS fact_electoral_membership (
    membership_id VARCHAR(100) PRIMARY KEY,
    person_id VARCHAR(100) NOT NULL REFERENCES dim_person(person_id) ON DELETE CASCADE,
    location_id INT REFERENCES dim_geography(location_id),
    year INT NOT NULL,
    position VARCHAR(150) NOT NULL,
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

-- ============================================================================
-- 3. PERFORMANCE INDEXES
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_mem_person ON fact_electoral_membership(person_id);
CREATE INDEX IF NOT EXISTS idx_mem_year ON fact_electoral_membership(year);
CREATE INDEX IF NOT EXISTS idx_mem_location ON fact_electoral_membership(location_id);
CREATE INDEX IF NOT EXISTS idx_person_name ON dim_person(last_name, first_name);
CREATE INDEX IF NOT EXISTS idx_geo_province ON dim_geography(province_std);
CREATE INDEX IF NOT EXISTS idx_poverty_lookup ON fact_poverty_metric(year, location_id);