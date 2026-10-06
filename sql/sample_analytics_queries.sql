-- Query 1: Top 10 Most Entrenched Families by Province
-- Counts the total number of distinct elected positions held by a single surname in a specific province since 1987.
SELECT 
    g.province_std,
    p.last_name,
    COUNT(DISTINCT f.membership_id) AS total_positions_won,
    COUNT(DISTINCT p.person_id) AS unique_family_members,
    MIN(f.year) AS first_year_in_power,
    MAX(f.year) AS latest_year_in_power
FROM fact_electoral_membership f
JOIN dim_person p ON f.person_id = p.person_id
JOIN dim_geography g ON f.location_id = g.location_id
WHERE f.year >= 1987
GROUP BY g.province_std, p.last_name
HAVING COUNT(DISTINCT p.person_id) > 1 -- Must have more than 1 family member
ORDER BY total_positions_won DESC
LIMIT 10;

-- Query 2: Dynasty Presence vs. Provincial Poverty Incidence (2018)
-- Compares the poverty headcount ratio of a province to the number of dynastic politicians active in that same year.
WITH DynastyCounts AS (
    SELECT 
        g.province_std,
        f.year,
        COUNT(DISTINCT p.last_name) AS unique_dynasties,
        COUNT(DISTINCT p.person_id) AS total_dynasty_members
    FROM fact_electoral_membership f
    JOIN dim_person p ON f.person_id = p.person_id
    JOIN dim_geography g ON f.location_id = g.location_id
    WHERE f.year = 2018 AND g.town_std IS NULL
    GROUP BY g.province_std, f.year
)
SELECT 
    d.province_std,
    d.unique_dynasties,
    d.total_dynasty_members,
    pov.poverty_incidence AS poverty_rate_2018
FROM DynastyCounts d
JOIN dim_geography g ON d.province_std = g.province_std AND g.town_std IS NULL
JOIN fact_poverty_metric pov ON g.location_id = pov.location_id AND pov.year = 2018
ORDER BY pov.poverty_incidence DESC;