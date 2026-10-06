# Philippine Political Dynasty ERD

```mermaid
erDiagram
    dim_person ||--o{ fact_electoral_membership : "holds"
    dim_geography ||--o{ fact_electoral_membership : "occurs_in"
    dim_geography ||--o{ fact_election_winner : "recorded_at"
    dim_geography ||--o{ fact_legislative_tenure : "represents"
    dim_geography ||--o{ fact_poverty_metric : "measured_at"

    dim_person {
        string person_id PK
        string first_name
        string last_name
        string middle_name
        string name_suffix
        string sex
        boolean suffix_suspect
    }

    dim_geography {
        int location_id PK
        string province_std
        string town_std
        string region
        boolean is_city
    }

    fact_electoral_membership {
        string membership_id PK
        string person_id FK
        int location_id FK
        int year
        string position
        string locality_source
    }

    fact_election_winner {
        int winner_id PK
        int location_id FK
        int year
        string position
        string last_name
        string first_name
        string party
        boolean town_shift_suspect
    }

    fact_legislative_tenure {
        int tenure_id PK
        int location_id FK
        string legislator_name
        int congress_number
        int start_year
        int end_year
        boolean is_party_list
    }

    fact_poverty_metric {
        int poverty_id PK
        int location_id FK
        int year
        string area_key
        decimal poverty_incidence
    }