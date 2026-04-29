"""AI 岗位匹配器 — 调用豆包 API"""
import json
import math
from typing import List, Optional

from backend.utils.logger import logger


def _safe_k(v) -> str:
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return ""
        return f"{int(f) // 1000}k"
    except (TypeError, ValueError):
        return ""


def _fuzzy_quick_score(resume_data: dict, job: dict) -> float:
    try:
        from thefuzz import fuzz
        resume_skills = [s.lower().strip() for s in resume_data.get("skills", []) if s]
        job_skills_raw = job.get("skills", "[]")
        try:
            job_skills = json.loads(job_skills_raw) if isinstance(job_skills_raw, str) else job_skills_raw
        except Exception:
            job_skills = []
        job_skills = [s.lower().strip() for s in job_skills if s]

        if not job_skills:
            skill_score = 50.0
        elif not resume_skills:
            skill_score = 0.0
        else:
            hits = sum(
                1 for js in job_skills
                if any(fuzz.partial_ratio(rs, js) >= 60 for rs in resume_skills)
            )
            skill_score = hits / len(job_skills) * 100
    except ImportError:
        skill_score = 50.0

    try:
        sal_min = job.get("salary_min")
        sal_max = job.get("salary_max")
        avg = float(sal_min or 0)
        if sal_min and sal_max:
            avg = (float(sal_min) + float(sal_max)) / 2
        salary_score = min(100.0, max(0.0, (avg - 1000) / 19000 * 100)) if avg else 30.0
    except Exception:
        salary_score = 30.0

    return round(skill_score * 0.7 + salary_score * 0.3, 1)


_MATCH_SYSTEM = """\
你是一名专业的招聘顾问，负责评估求职者简历与目标岗位的匹配程度。
请根据以下信息进行深度语义匹配分析，并以 JSON 格式输出结果。

评分维度：
- skill_score（0-100）：技术技能与JD要求的重合程度（权重40%）
- fit_score（0-100）：经历、背景、学历与岗位整体需求的契合度（权重40%）
- salary_score（0-100）：薪资范围的吸引力（无薪资给50分；权重20%）

综合分 = skill_score * 0.4 + fit_score * 0.4 + salary_score * 0.2

输出 JSON（只输出 JSON，不要任何解释）：
{
  "total_score": <0-100整数>,
  "skill_score": <0-100>,
  "fit_score": <0-100>,
  "salary_score": <0-100>,
  "matched_skills": ["技能1", "技能2"],
  "missing_skills": ["技能1", "技能2"],
  "analysis": "2-3句综合分析",
  "strengths": ["优势1", "优势2"],
  "suggestions": ["建议1", "建议2"]
}"""


class AIJobMatcher:
    def __init__(self, config):
        self.config = config

    def match_single(self, resume_data: dict, job: dict) -> dict:
        desc = str(job.get("description", "")).strip()
        if len(desc) < 20:
            return self._fallback(resume_data, job, "JD未获取，使用模糊评分")

        lo = _safe_k(job.get("salary_min"))
        hi = _safe_k(job.get("salary_max"))
        salary_str = f"{lo}–{hi}" if lo and hi else (lo or hi or "面议")

        resume_text = resume_data.get("_raw_text", "")
        if not resume_text:
            parts = []
            if resume_data.get("name"):
                parts.append(f"姓名：{resume_data['name']}")
            if resume_data.get("skills"):
                parts.append("技能：" + "、".join(resume_data["skills"]))
            if resume_data.get("work_experience"):
                for exp in resume_data["work_experience"]:
                    parts.append(f"经历：{exp.get('company','')} {exp.get('position','')} - {exp.get('description','')[:200]}")
            if resume_data.get("project_experience"):
                for proj in resume_data["project_experience"]:
                    parts.append(f"项目：{proj.get('name','')} - {proj.get('description','')[:200]}")
            resume_text = "\n".join(parts)

        prompt = (
            f"【求职者简历】\n{resume_text[:3000]}\n\n"
            f"【目标岗位】\n"
            f"职位：{job.get('title', '')}\n"
            f"公司：{job.get('company', '')}\n"
            f"城市：{job.get('city', '')}\n"
            f"薪资：{salary_str}\n\n"
            f"【岗位描述（JD）】\n{desc[:3000]}"
        )

        try:
            client = self.config.make_doubao_client()
            result = client.chat_json(
                messages=[{"role": "user", "content": prompt}],
                system=_MATCH_SYSTEM,
                max_tokens=1024,
                temperature=0.1,
            )
            skill = float(result.get("skill_score", 50))
            fit = float(result.get("fit_score", 50))
            sal = float(result.get("salary_score", 30))
            result["total_score"] = round(skill * 0.4 + fit * 0.4 + sal * 0.2, 1)
            return result
        except Exception as e:
            err = str(e)
            reason = "API超时" if "timeout" in err.lower() else "API异常"
            return self._fallback(resume_data, job, reason)

    def batch_match(self, resume_data: dict, jobs: List[dict]) -> List[dict]:
        results = []
        for job in jobs:
            analysis = self.match_single(resume_data, job)
            results.append({
                **job,
                "match_score": analysis["total_score"],
                "skill_score": analysis.get("skill_score", 0),
                "fit_score": analysis.get("fit_score", 0),
                "salary_score": analysis.get("salary_score", 0),
                "matched_skills": "、".join(analysis.get("matched_skills", [])) or "—",
                "missing_skills": "、".join(analysis.get("missing_skills", [])[:5]) or "—",
                "ai_analysis": analysis.get("analysis", ""),
                "ai_strengths": json.dumps(analysis.get("strengths", []), ensure_ascii=False),
                "ai_suggestions": json.dumps(analysis.get("suggestions", []), ensure_ascii=False),
            })
        return sorted(results, key=lambda x: x["match_score"], reverse=True)

    def _fallback(self, resume_data: dict, job: dict, reason: str = "AI不可用") -> dict:
        score = _fuzzy_quick_score(resume_data, job)
        return {
            "total_score": score,
            "skill_score": score,
            "fit_score": score,
            "salary_score": 30,
            "matched_skills": [],
            "missing_skills": [],
            "analysis": f"AI分析降级（{reason}），使用快速模糊评分",
            "strengths": [],
            "suggestions": [],
        }
