"""SQLite 数据库管理"""
import sqlite3
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, List

from backend.core.config import DB_PATH
from backend.utils.date_utils import now_iso, today_str
from backend.utils.logger import logger


class Database:
    """SQLite 数据库操作类"""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = str(db_path)
        self.init_schema()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = lambda cursor, row: dict(
            (col[0], row[idx]) for idx, col in enumerate(cursor.description)
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self):
        schema_path = Path(__file__).parent / "migrations" / "init_schema.sql"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        with self.get_connection() as conn:
            conn.executescript(schema_sql)
            for migration_sql in [
                "ALTER TABLE jobs ADD COLUMN is_retained INTEGER DEFAULT 0",
                "ALTER TABLE user_resumes ADD COLUMN avatar_path TEXT",
                # 允许 applications.job_id 为 NULL（外部链接投递无关联岗位）
                # SQLite 不支持 ALTER COLUMN，通过新列兼容
                "ALTER TABLE applications ADD COLUMN job_url TEXT",
                "ALTER TABLE applications ADD COLUMN job_title TEXT",
            ]:
                try:
                    conn.execute(migration_sql)
                except Exception:
                    pass
            # 检查 applications 表的 job_id 是否允许 NULL
            # 如果不允许，重建表以兼容外部链接投递
            try:
                col_info = conn.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='applications'"
                ).fetchone()
                sql_text = col_info.get('sql', '') if col_info else ''
                # 精确匹配：job_id 后面跟着 NOT NULL（说明是旧表结构）
                import re
                if re.search(r'job_id\s+INTEGER\s+NOT\s+NULL', sql_text):
                    logger.info("检测到 applications.job_id 为 NOT NULL，开始迁移...")
                    conn.executescript("""
                        CREATE TABLE IF NOT EXISTS applications_new (
                            id              INTEGER PRIMARY KEY AUTOINCREMENT,
                            job_id          INTEGER,
                            tailored_resume_id INTEGER,
                            method          TEXT NOT NULL,
                            status          TEXT DEFAULT 'pending',
                            error_message   TEXT,
                            job_url         TEXT,
                            job_title       TEXT,
                            applied_at      TEXT,
                            updated_at      TEXT,
                            FOREIGN KEY (job_id) REFERENCES jobs(id),
                            FOREIGN KEY (tailored_resume_id) REFERENCES tailored_resumes(id)
                        );
                        INSERT OR IGNORE INTO applications_new
                            SELECT id, job_id, tailored_resume_id, method, status,
                                   error_message, '', '', applied_at, updated_at
                            FROM applications;
                        DROP TABLE applications;
                        ALTER TABLE applications_new RENAME TO applications;
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status)")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_applications_applied_at ON applications(applied_at)")
                    logger.info("applications 表迁移完成，job_id 已改为允许 NULL")
            except Exception as e:
                logger.warning(f"applications 表迁移检查失败（可能已是正确结构）: {e}")
        logger.info("数据库初始化完成")

    # ==================== 岗位操作 ====================

    def insert_jobs(self, jobs: List[dict]) -> int:
        if not jobs:
            return 0
        inserted = 0
        with self.get_connection() as conn:
            for job in jobs:
                if not job.get("title") and not job.get("company"):
                    continue
                try:
                    cursor = conn.execute(
                        """INSERT OR IGNORE INTO jobs
                        (platform, job_id, title, company, city, district,
                         salary_min, salary_max, education, experience,
                         industry, skills, description, url, contact_email,
                         company_size, posted_date, scraped_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            job.get("platform", ""),
                            job.get("job_id", ""),
                            job.get("title", ""),
                            job.get("company", ""),
                            job.get("city", ""),
                            job.get("district", ""),
                            job.get("salary_min"),
                            job.get("salary_max"),
                            job.get("education", "不限"),
                            job.get("experience", ""),
                            job.get("industry", ""),
                            json.dumps(job.get("skills", []), ensure_ascii=False),
                            job.get("description", ""),
                            job.get("url", ""),
                            job.get("contact_email", ""),
                            job.get("company_size", ""),
                            job.get("posted_date", ""),
                            job.get("scraped_at", now_iso()),
                        ),
                    )
                    if cursor.rowcount == 1:
                        inserted += 1
                except sqlite3.IntegrityError:
                    pass
                except Exception as e:
                    logger.warning(f"插入岗位失败: {e} | job={job.get('title','')}")
        logger.info(f"插入 {inserted}/{len(jobs)} 条岗位数据")
        return inserted

    def query_jobs(self, filters: Optional[dict] = None) -> List[dict]:
        query = "SELECT * FROM jobs WHERE is_active = 1"
        params = []
        if filters:
            if filters.get("platform"):
                query += " AND platform = ?"
                params.append(filters["platform"])
            if filters.get("city"):
                query += " AND city LIKE ?"
                params.append(f"%{filters['city']}%")
            if filters.get("keyword"):
                query += " AND (title LIKE ? OR description LIKE ?)"
                params.extend([f"%{filters['keyword']}%"] * 2)
            if filters.get("retained_only"):
                query += " AND is_retained = 1"
        query += " ORDER BY scraped_at DESC"
        with self.get_connection() as conn:
            return conn.execute(query, params).fetchall()

    def delete_job(self, job_id: int):
        with self.get_connection() as conn:
            conn.execute("UPDATE jobs SET is_active = 0 WHERE id = ?", (job_id,))

    def retain_job(self, job_id: int):
        with self.get_connection() as conn:
            conn.execute("UPDATE jobs SET is_retained = 1 WHERE id = ?", (job_id,))

    def unretain_job(self, job_id: int):
        with self.get_connection() as conn:
            conn.execute("UPDATE jobs SET is_retained = 0 WHERE id = ?", (job_id,))

    def update_job_description(self, job_id: int, description: str):
        with self.get_connection() as conn:
            conn.execute("UPDATE jobs SET description = ? WHERE id = ?", (description, job_id))

    def get_job_by_id(self, job_id: int) -> Optional[dict]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None

    def hard_clear_jobs(self):
        with self.get_connection() as conn:
            conn.execute("DELETE FROM jobs")

    # ==================== 简历操作 ====================

    def upsert_resume(self, resume_data: dict) -> int:
        with self.get_connection() as conn:
            if resume_data.get("is_primary"):
                conn.execute("UPDATE user_resumes SET is_primary = 0")
            existing = conn.execute(
                "SELECT id FROM user_resumes WHERE file_path = ?",
                (resume_data["file_path"],),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE user_resumes SET parsed_data = ?, is_primary = ?,
                       updated_at = ? WHERE id = ?""",
                    (resume_data.get("parsed_data", ""),
                     1 if resume_data.get("is_primary") else 0,
                     now_iso(), existing["id"]),
                )
                return existing["id"]
            else:
                cursor = conn.execute(
                    """INSERT INTO user_resumes
                    (file_name, file_path, file_type, parsed_data, is_primary, uploaded_at)
                    VALUES (?,?,?,?,?,?)""",
                    (resume_data["file_name"], resume_data["file_path"],
                     resume_data["file_type"], resume_data.get("parsed_data", ""),
                     1 if resume_data.get("is_primary") else 0, now_iso()),
                )
                return cursor.lastrowid

    def update_resume_parsed_data(self, resume_id: int, parsed_data_json: str):
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE user_resumes SET parsed_data = ?, updated_at = ? WHERE id = ?",
                (parsed_data_json, now_iso(), resume_id),
            )

    def update_resume_avatar(self, resume_id: int, avatar_path: str):
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE user_resumes SET avatar_path = ?, updated_at = ? WHERE id = ?",
                (avatar_path, now_iso(), resume_id),
            )

    def delete_resume(self, resume_id: int):
        with self.get_connection() as conn:
            # 先删除关联的定制简历（解除外键约束）
            conn.execute("DELETE FROM tailored_resumes WHERE base_resume_id = ?", (resume_id,))
            conn.execute("DELETE FROM user_resumes WHERE id = ?", (resume_id,))

    def get_primary_resume(self) -> Optional[dict]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM user_resumes WHERE is_primary = 1").fetchone()
            return dict(row) if row else None

    def get_all_resumes(self) -> List[dict]:
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM user_resumes ORDER BY uploaded_at DESC").fetchall()
            return [dict(r) for r in rows]

    def set_primary_resume(self, resume_id: int):
        with self.get_connection() as conn:
            conn.execute("UPDATE user_resumes SET is_primary = 0")
            conn.execute("UPDATE user_resumes SET is_primary = 1 WHERE id = ?", (resume_id,))

    # ==================== 定制简历操作 ====================

    def insert_tailored_resume(self, data: dict) -> int:
        with self.get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO tailored_resumes
                (base_resume_id, job_id, file_name, file_path, changes_json, status, created_at)
                VALUES (?,?,?,?,?,?,?)""",
                (data["base_resume_id"], data["job_id"], data["file_name"],
                 data["file_path"], data.get("changes_json", ""),
                 data.get("status", "draft"), now_iso()),
            )
            return cursor.lastrowid

    def get_tailored_resumes(self, limit: int = 50) -> List[dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                """SELECT tr.*, j.title as job_title, j.company as job_company
                   FROM tailored_resumes tr
                   LEFT JOIN jobs j ON tr.job_id = j.id
                   ORDER BY tr.created_at DESC LIMIT ?""",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ==================== 投递操作 ====================

    def insert_application(self, data: dict) -> int:
        with self.get_connection() as conn:
            # 如果 job_id 为 None，设为 NULL（外部链接投递如实习僧）
            job_id = data.get("job_id")
            cursor = conn.execute(
                """INSERT INTO applications
                (job_id, tailored_resume_id, method, status, error_message,
                 job_url, job_title, applied_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (job_id, data.get("tailored_resume_id"), data["method"],
                 data.get("status", "pending"), data.get("error_message", ""),
                 data.get("job_url", ""), data.get("job_title", ""),
                 now_iso(), now_iso()),
            )
            return cursor.lastrowid

    def update_application_status(self, app_id: int, status: str, error: str = ""):
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE applications SET status = ?, error_message = ?, updated_at = ? WHERE id = ?",
                (status, error, now_iso(), app_id),
            )

    def get_applications(self, limit: int = 100) -> List[dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                """SELECT a.*, j.title, j.company, j.city, j.url as job_url_from_jobs
                   FROM applications a
                   LEFT JOIN jobs j ON a.job_id = j.id
                   ORDER BY a.applied_at DESC LIMIT ?""",
                (limit,)
            ).fetchall()
            results = []
            for r in rows:
                r = dict(r)
                # 优先使用 jobs 表的 title，否则使用 applications 表的 job_title
                if not r.get('title') and r.get('job_title'):
                    r['title'] = r['job_title']
                # 优先使用 jobs 表的 url，否则使用 applications 表的 job_url
                if not r.get('job_url_from_jobs') and r.get('job_url'):
                    r['url'] = r['job_url']
                elif r.get('job_url_from_jobs'):
                    r['url'] = r['job_url_from_jobs']
                if 'job_url_from_jobs' in r:
                    del r['job_url_from_jobs']
                results.append(r)
            return results

    # ==================== 面试记忆操作 ====================

    def insert_interview_session(self, data: dict) -> int:
        with self.get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO interview_sessions
                (session_id, mode, topic, started_at, ended_at, duration_sec,
                 messages, score, feedback_json, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (data["session_id"], data.get("mode", "text"), data.get("topic", ""),
                 data.get("started_at", now_iso()), data.get("ended_at"),
                 data.get("duration_sec", 0), data.get("messages", "[]"),
                 data.get("score"), data.get("feedback_json", "{}"),
                 now_iso()),
            )
            return cursor.lastrowid

    def get_interview_sessions(self, limit: int = 50) -> List[dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM interview_sessions ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_interview_session(self, session_id: str) -> Optional[dict]:
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM interview_sessions WHERE session_id = ?",
                (session_id,)
            ).fetchone()
            return dict(row) if row else None

    def delete_interview_session(self, session_id: str):
        with self.get_connection() as conn:
            conn.execute(
                "DELETE FROM interview_sessions WHERE session_id = ?",
                (session_id,)
            )

    # ==================== 统计 ====================

    def get_daily_stats(self) -> dict:
        date = today_str()
        with self.get_connection() as conn:
            scraped = (conn.execute(
                "SELECT COUNT(*) AS n FROM jobs WHERE DATE(scraped_at) = ?", (date,)
            ).fetchone() or {}).get("n", 0)
            matched = (conn.execute(
                "SELECT COUNT(DISTINCT job_id) AS n FROM tailored_resumes WHERE DATE(created_at) = ?",
                (date,),
            ).fetchone() or {}).get("n", 0)
            applied = (conn.execute(
                "SELECT COUNT(*) AS n FROM applications WHERE DATE(applied_at) = ? AND status = 'submitted'",
                (date,),
            ).fetchone() or {}).get("n", 0)
        return {"date": date, "jobs_scraped": scraped, "jobs_matched": matched, "jobs_applied": applied}

    def insert_scrape_log(self, data: dict) -> int:
        with self.get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO scrape_logs
                (platform, keyword, city, jobs_found, status, error_message, started_at, finished_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (data["platform"], data["keyword"], data.get("city", ""),
                 data.get("jobs_found", 0), data.get("status", "success"),
                 data.get("error_message", ""), data.get("started_at", now_iso()),
                 data.get("finished_at")),
            )
            return cursor.lastrowid

    # ==================== 岗位匹配结果操作 ====================

    def upsert_match_result(self, data: dict):
        with self.get_connection() as conn:
            conn.execute(
                """INSERT INTO match_results
                (resume_id, job_id, match_score, skill_score, fit_score, salary_score,
                 matched_skills, missing_skills, ai_analysis, ai_strengths, ai_suggestions,
                 jd_missing, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(resume_id, job_id) DO UPDATE SET
                  match_score=excluded.match_score,
                  skill_score=excluded.skill_score,
                  fit_score=excluded.fit_score,
                  salary_score=excluded.salary_score,
                  matched_skills=excluded.matched_skills,
                  missing_skills=excluded.missing_skills,
                  ai_analysis=excluded.ai_analysis,
                  ai_strengths=excluded.ai_strengths,
                  ai_suggestions=excluded.ai_suggestions,
                  jd_missing=excluded.jd_missing,
                  created_at=excluded.created_at""",
                (
                    data["resume_id"], data["job_id"],
                    data.get("match_score", 0), data.get("skill_score", 0),
                    data.get("fit_score", 0), data.get("salary_score", 0),
                    json.dumps(data.get("matched_skills", []), ensure_ascii=False),
                    json.dumps(data.get("missing_skills", []), ensure_ascii=False),
                    data.get("ai_analysis", ""), data.get("ai_strengths", ""),
                    data.get("ai_suggestions", ""),
                    1 if data.get("jd_missing") else 0,
                    now_iso(),
                ),
            )

    def get_retained_jobs_with_scores(self, resume_id: int) -> List[dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                """SELECT j.*, mr.match_score, mr.skill_score, mr.fit_score,
                          mr.salary_score, mr.matched_skills, mr.missing_skills,
                          mr.ai_analysis, mr.ai_strengths, mr.ai_suggestions,
                          mr.jd_missing, mr.created_at as score_at
                   FROM jobs j
                   LEFT JOIN match_results mr ON j.id = mr.job_id AND mr.resume_id = ?
                   WHERE j.is_retained = 1 AND j.is_active = 1
                   ORDER BY COALESCE(mr.match_score, -1) DESC""",
                (resume_id,),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                for field in ("matched_skills", "missing_skills"):
                    if isinstance(d.get(field), str):
                        try:
                            d[field] = json.loads(d[field])
                        except Exception:
                            d[field] = []
                if isinstance(d.get("skills"), str):
                    try:
                        d["skills"] = json.loads(d["skills"])
                    except Exception:
                        d["skills"] = []
                result.append(d)
            return result

    # ==================== 数据统计 ====================

    def get_stats_overview(self) -> dict:
        date = today_str()
        with self.get_connection() as conn:
            total_jobs = (conn.execute(
                "SELECT COUNT(*) AS n FROM jobs WHERE is_active = 1"
            ).fetchone() or {}).get("n", 0)
            retained_jobs = (conn.execute(
                "SELECT COUNT(*) AS n FROM jobs WHERE is_retained = 1 AND is_active = 1"
            ).fetchone() or {}).get("n", 0)
            today_scraped = (conn.execute(
                "SELECT COUNT(*) AS n FROM jobs WHERE DATE(scraped_at) = ?", (date,)
            ).fetchone() or {}).get("n", 0)
            total_tailored = (conn.execute(
                "SELECT COUNT(*) AS n FROM tailored_resumes"
            ).fetchone() or {}).get("n", 0)
            total_applied = (conn.execute(
                "SELECT COUNT(*) AS n FROM applications WHERE status = 'submitted'"
            ).fetchone() or {}).get("n", 0)
            total_matched = (conn.execute(
                "SELECT COUNT(*) AS n FROM match_results"
            ).fetchone() or {}).get("n", 0)
        return {
            "total_jobs": total_jobs,
            "retained_jobs": retained_jobs,
            "today_scraped": today_scraped,
            "total_tailored": total_tailored,
            "total_applied": total_applied,
            "total_matched": total_matched,
        }

    def get_stats_trends(self, days: int = 7) -> List[dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                """SELECT DATE(scraped_at) as date, COUNT(*) as jobs_scraped
                   FROM jobs
                   WHERE DATE(scraped_at) >= DATE('now', ? || ' days')
                   GROUP BY DATE(scraped_at)
                   ORDER BY date""",
                (f"-{days}",),
            ).fetchall()
            scraped_map = {r["date"]: r["jobs_scraped"] for r in rows}

            rows2 = conn.execute(
                """SELECT DATE(applied_at) as date, COUNT(*) as jobs_applied
                   FROM applications
                   WHERE status = 'submitted'
                     AND DATE(applied_at) >= DATE('now', ? || ' days')
                   GROUP BY DATE(applied_at)
                   ORDER BY date""",
                (f"-{days}",),
            ).fetchall()
            applied_map = {r["date"]: r["jobs_applied"] for r in rows2}

            rows3 = conn.execute(
                """SELECT DATE(created_at) as date, COUNT(*) as jobs_tailored
                   FROM tailored_resumes
                   WHERE DATE(created_at) >= DATE('now', ? || ' days')
                   GROUP BY DATE(created_at)
                   ORDER BY date""",
                (f"-{days}",),
            ).fetchall()
            tailored_map = {r["date"]: r["jobs_tailored"] for r in rows3}

        from datetime import date as date_type, timedelta
        import datetime as dt_module
        result = []
        today = dt_module.date.today()
        for i in range(days - 1, -1, -1):
            d = (today - timedelta(days=i)).isoformat()
            result.append({
                "date": d,
                "jobs_scraped": scraped_map.get(d, 0),
                "jobs_applied": applied_map.get(d, 0),
                "jobs_tailored": tailored_map.get(d, 0),
            })
        return result

    def get_stats_platform_distribution(self) -> List[dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                """SELECT platform, COUNT(*) as count
                   FROM jobs WHERE is_active = 1
                   GROUP BY platform ORDER BY count DESC"""
            ).fetchall()
            return [dict(r) for r in rows]

    def get_stats_application_status(self) -> List[dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                """SELECT status, COUNT(*) as count
                   FROM applications
                   GROUP BY status ORDER BY count DESC"""
            ).fetchall()
            return [dict(r) for r in rows]
