-- ============================================================================
-- Query 1: Top 10 Most Entrenched Dynastic Clans by Province
-- Uses the validated Kinship Engine (dim_clan & fact_person_clan) rather than 
-- raw surname grouping to avoid false-positive conflation of common surnames.
-- ============================================================================
SELECT 
    g.province_std,
    c.clan_surname,
    c.clan_id,
    COUNT(DISTINCT f.membership_id) AS total_positions_won,
    COUNT(DISTINCT p.person_id) AS unique_dynasty_members,
    MIN(f.year) AS first_year_in_power,
    MAX(f.year) AS latest_year_in_power
FROM fact_electoral_membership f
JOIN dim_person p ON f.person_id = p.person_id
JOIN fact_person_clan fpc ON p.person_id = fpc.person_id
JOIN dim_clan c ON fpc.clan_id = c.clan_id
JOIN dim_geography g ON f.location_id = g.location_id
WHERE f.year >= 1987
GROUP BY g.province_std, c.clan_surname, c.clan_id
HAVING COUNT(DISTINCT p.person_id) > 1
ORDER BY total_positions_won DESC
LIMIT 10;

-- ============================================================================
-- Query 2: Dynastic Concentration (2016 Term Active in 2018) vs. Provincial Poverty
-- Correlates officials active during the 2018 PSA census with provincial poverty.
-- ============================================================================
WITH Active2018Dynasties AS (
    SELECT 
        g.province_std,
        COUNT(DISTINCT c.clan_id) AS active_dynastic_clans,
        COUNT(DISTINCT p.person_id) AS total_dynasty_officials
    FROM fact_electoral_membership f
    JOIN dim_person p ON f.person_id = p.person_id
    JOIN fact_person_clan fpc ON p.person_id = fpc.person_id
    JOIN dim_clan c ON fpc.clan_id = c.clan_id
    JOIN dim_geography g ON f.location_id = g.location_id
    WHERE f.year = 2016
    GROUP BY g.province_std
)
SELECT 
    ad.province_std,
    ad.active_dynastic_clans,
    ad.total_dynasty_officials,
    pov.poverty_incidence AS poverty_incidence_2018
FROM Active2018Dynasties ad
JOIN dim_geography g ON ad.province_std = g.province_std AND g.town_std IS NULL
JOIN fact_poverty_metric pov ON g.location_id = pov.location_id 
    AND pov.year = 2018 
    AND pov.level = 'province'
ORDER BY pov.poverty_incidence DESC;