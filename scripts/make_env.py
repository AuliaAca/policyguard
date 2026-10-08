"""Membuat atau memperbarui file .env, supaya tidak perlu mengedit .env dengan tangan.

Pemakaian:
    python scripts/make_env.py local          # tanpa Docker: SQLite, tanpa Redis, tanpa AI
    python scripts/make_env.py local --ai     # tanpa Docker, dengan AI (meminta OPENAI_API_KEY)
    python scripts/make_env.py docker         # untuk docker compose, tanpa AI
    python scripts/make_env.py docker --ai    # untuk docker compose, dengan AI

Nilai yang sudah ada di .env (API key, OPENAI_API_KEY, model, threshold) dipertahankan.
"""
import argparse
import getpass
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"

TARGETS = {
    "local": {"DATABASE_URL": "sqlite:///./policyguard.db", "REDIS_URL": ""},
    "docker": {"DATABASE_URL": "postgresql+psycopg://policyguard:policyguard@postgres:5432/policyguard",
               "REDIS_URL": "redis://redis:6379/0"},
}
KEEP = ["SERVICE_API_KEYS", "DASHBOARD_API_KEY", "OPENAI_API_KEY", "LLM_MODEL", "LLM_TEMPERATURE",
        "RETRIEVAL_MODE", "RETRIEVAL_TOP_K", "EMBEDDING_PROVIDER", "EMBEDDING_MODEL", "T_REJECT", "T_APPROVE"]
DEFAULTS = {"LLM_MODEL": "gpt-4o-mini", "LLM_TEMPERATURE": "0", "RETRIEVAL_MODE": "topk", "RETRIEVAL_TOP_K": "5",
            "EMBEDDING_PROVIDER": "openai", "EMBEDDING_MODEL": "text-embedding-3-small",
            "T_REJECT": "0.8", "T_APPROVE": "0.8"}


def read_env(path: Path) -> dict[str, str]:
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    return values


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", choices=["local", "docker"])
    ap.add_argument("--ai", action="store_true", help="aktifkan mode LLM (butuh OPENAI_API_KEY)")
    args = ap.parse_args()

    old = read_env(ENV)
    new = {k: old[k] for k in KEEP if old.get(k)}
    for k, v in DEFAULTS.items():
        new.setdefault(k, v)
    if "SERVICE_API_KEYS" not in new:
        dash = "dash-" + secrets.token_urlsafe(12)
        new["SERVICE_API_KEYS"] = f"dev-{secrets.token_urlsafe(12)},{dash}"
        new["DASHBOARD_API_KEY"] = dash
    new.setdefault("DASHBOARD_API_KEY", new["SERVICE_API_KEYS"].split(",")[-1].strip())

    if args.ai and not new.get("OPENAI_API_KEY"):
        key = getpass.getpass("Tempel OPENAI_API_KEY (tidak akan terlihat saat diketik), lalu Enter: ").strip()
        if not key:
            raise SystemExit("OPENAI_API_KEY kosong. .env tidak diubah.")
        new["OPENAI_API_KEY"] = key
    new["PIPELINE_MODE"] = "llm" if args.ai else "rules_only"
    new.update(TARGETS[args.target])
    new["LOG_LEVEL"] = old.get("LOG_LEVEL", "INFO")

    order = ["DATABASE_URL", "REDIS_URL", "SERVICE_API_KEYS", "DASHBOARD_API_KEY", "PIPELINE_MODE",
             "OPENAI_API_KEY", *DEFAULTS, "LOG_LEVEL"]
    lines = ["# Dibuat oleh scripts/make_env.py. JANGAN di-commit ke git (sudah ada di .gitignore)."]
    lines += [f"{k}={new.get(k, '')}" for k in dict.fromkeys(order)]
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")

    first_key = new["SERVICE_API_KEYS"].split(",")[0].strip()
    openai = new.get("OPENAI_API_KEY", "")
    print(f".env ditulis untuk mode '{args.target}' ({'dengan AI' if args.ai else 'tanpa AI'}).")
    print(f"  API key (untuk halaman /docs): {first_key}")
    print(f"  OPENAI_API_KEY               : {'terisi (' + openai[:6] + '...)' if openai else 'kosong'}")


if __name__ == "__main__":
    main()
