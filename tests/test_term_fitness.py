import pytest
from datetime import date, timedelta
from job_crawler.db import repository

def test_term_starts_with_neutral_score(tmp_db):
    """After seeding from config, all terms should have fitness_score = 0.5."""
    from job_crawler.config import load_config
    config = load_config()

    terms_config = {
        "priority_terms": config.priority_terms,
        "categories": config.categories,
        "boolean_searches": config.boolean_searches,
    }
    count = repository.load_terms_from_config(terms_config, tmp_db)
    assert count > 0

    import sqlite3
    with sqlite3.connect(str(tmp_db)) as conn:
        rows = conn.execute("SELECT fitness_score FROM search_terms").fetchall()

    assert all(row[0] == 0.5 for row in rows), "All terms should start at 0.5"

def test_positive_feedback_increases_fitness(tmp_db):
    """After positive feedback, term fitness should increase above 0.5."""
    import sqlite3
    with sqlite3.connect(str(tmp_db)) as conn:
        conn.execute(
            "INSERT INTO search_terms (term, category, fitness_score) VALUES (?, ?, 0.5)",
            ("VP eCommerce", "executive_leadership")
        )
        conn.commit()
        term_id = conn.execute("SELECT id FROM search_terms WHERE term = ?", ("VP eCommerce",)).fetchone()[0]

    repository.update_term_fitness(term_id, is_positive=True, db_path=tmp_db)

    import sqlite3
    with sqlite3.connect(str(tmp_db)) as conn:
        row = conn.execute("SELECT fitness_score, feedback_positive FROM search_terms WHERE id = ?", (term_id,)).fetchone()

    assert row[1] == 1  # feedback_positive incremented
    assert row[0] == 1.0  # 1 positive / (1 pos + 0 neg) = 1.0

def test_negative_feedback_decreases_fitness(tmp_db):
    """After negative feedback, term fitness should decrease below 0.5."""
    import sqlite3
    with sqlite3.connect(str(tmp_db)) as conn:
        conn.execute(
            "INSERT INTO search_terms (term, category, fitness_score) VALUES (?, ?, 0.5)",
            ("Junior Coordinator", "test")
        )
        conn.commit()
        term_id = conn.execute("SELECT id FROM search_terms WHERE term = ?", ("Junior Coordinator",)).fetchone()[0]

    repository.update_term_fitness(term_id, is_positive=False, db_path=tmp_db)

    with sqlite3.connect(str(tmp_db)) as conn:
        row = conn.execute("SELECT fitness_score, feedback_negative FROM search_terms WHERE id = ?", (term_id,)).fetchone()

    assert row[1] == 1  # feedback_negative incremented
    assert row[0] == 0.0  # 0 positive / (0 pos + 1 neg) = 0.0

def test_next_run_date_daily_for_high_fitness(tmp_db):
    """Terms with fitness >= 0.70 should be scheduled daily."""
    import sqlite3
    with sqlite3.connect(str(tmp_db)) as conn:
        conn.execute(
            "INSERT INTO search_terms (term, feedback_positive, feedback_negative, fitness_score) VALUES (?, 7, 1, 0.875)",
            ("High Fitness Term",)
        )
        conn.commit()
        term_id = conn.execute("SELECT id FROM search_terms WHERE term = ?", ("High Fitness Term",)).fetchone()[0]

    # Add one more positive to trigger recalc
    repository.update_term_fitness(term_id, is_positive=True, db_path=tmp_db)

    with sqlite3.connect(str(tmp_db)) as conn:
        row = conn.execute("SELECT next_run_date FROM search_terms WHERE id = ?", (term_id,)).fetchone()

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert row[0] == tomorrow

def test_load_terms_is_idempotent(tmp_db):
    """Loading terms twice should not create duplicates."""
    from job_crawler.config import load_config
    config = load_config()
    terms_config = {
        "priority_terms": config.priority_terms,
        "categories": config.categories,
        "boolean_searches": config.boolean_searches,
    }

    count1 = repository.load_terms_from_config(terms_config, tmp_db)
    count2 = repository.load_terms_from_config(terms_config, tmp_db)

    assert count2 == 0, "Second load should insert 0 new terms (all already exist)"

    import sqlite3
    with sqlite3.connect(str(tmp_db)) as conn:
        total = conn.execute("SELECT COUNT(*) FROM search_terms").fetchone()[0]

    assert total == count1  # No duplicates
