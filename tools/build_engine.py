r"""Build the HOWO WD615-class engine in a running Delta3D service and export the results.

Run with the Delta3D virtual environment so the engine layout code is importable:

    & "C:\Users\ICT\Untitled project\.venv\Scripts\python.exe" tools\build_engine.py

Credentials come from DELTA_USER / DELTA_PASSWORD (never from arguments). The script is
idempotent: it reuses the project, regenerates only parts whose specification changed, updates
the assemblies in place and rebuilds them. Outputs are written to ``outputs/``.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
DELTA_ROOT = Path(os.getenv("DELTA3D_ROOT", r"C:\Users\ICT\Untitled project"))
sys.path.insert(0, str(DELTA_ROOT / "backend"))

import httpx  # noqa: E402
from delta3d import __version__ as delta3d_version  # noqa: E402
from delta3d import engine_layout as layout  # noqa: E402
from delta3d.domain import parse_spec  # noqa: E402

PROJECT_NAME = "HOWO WD615 engine (concept)"
DESCRIPTION = (
    "WD615-class 9.7 L in-line six diesel assembled from exact parametric solids. Headline "
    "dimensions follow published WD615 data; internal sizes are labelled assumptions. Parts are "
    "linked to the Buffalo (buffalo.co.ke) catalog for the bill of materials. Concept model: not "
    "OEM geometry, not validated for manufacture."
)
ASSEMBLIES = (
    ("WD615 engine · cylinder 1 TDC", 0.0),
    ("WD615 engine · 90° crank", 90.0),
)
REQUIREMENTS = [
    {
        "name": "Piston mass",
        "metric": "mass",
        "target": 2.3,
        "unit": "kg",
        "source": "Catalog piston VG1560037011A is 2.185 kg",
    },
]


def wait(client: httpx.Client, job_id: str, timeout: float) -> dict:
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in {"succeeded", "failed", "canceled"}:
            if job["state"] != "succeeded":
                raise RuntimeError(f"{job['kind']} job {job['state']}: {job.get('error')}")
            return job
        time.sleep(1.0)
    raise TimeoutError(f"Job {job_id} did not finish within {timeout} s.")


def login(client: httpx.Client) -> None:
    username = os.getenv("DELTA_USER")
    password = os.getenv("DELTA_PASSWORD")
    if not username or not password:
        raise SystemExit("Set DELTA_USER and DELTA_PASSWORD in the environment.")
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    response.raise_for_status()
    client.headers["X-Delta-CSRF"] = response.json()["csrf"]


def ensure_project(client: httpx.Client) -> str:
    for project in client.get("/api/projects").json():
        if project["name"] == PROJECT_NAME:
            return project["id"]
    project = client.post("/api/projects", json={"name": PROJECT_NAME, "description": DESCRIPTION})
    project.raise_for_status()
    project_id = project.json()["id"]
    client.put(
        f"/api/projects/{project_id}/requirements",
        json={"expected_version": 0, "requirements": REQUIREMENTS},
    ).raise_for_status()
    return project_id


def import_catalog(client: httpx.Client, project_id: str) -> dict:
    content = (PROJECT / "data" / "source" / "buffalo_parts.csv").read_text(encoding="utf-8")
    response = client.post(
        f"/api/projects/{project_id}/catalog",
        json={
            "csv": content,
            "source": "buffalo.co.ke scrape (buffalo_parts.csv)",
            "replace": True,
        },
        timeout=180,
    )
    response.raise_for_status()
    return response.json()


def sync_parts(client: httpx.Client, project_id: str, specs: dict) -> dict[str, str]:
    revisions: dict[str, str] = {}
    for part in client.get(f"/api/projects/{project_id}/parts").json():
        library = part["attributes"].get("library")
        if library and library not in revisions:
            revisions[library] = part["id"]
    pending = []
    for library, specification in specs.items():
        specification = {
            **specification,
            "attributes": {
                **specification["attributes"],
                "library": library,
                # A platform upgrade can change builders without changing parameters.
                "delta3d_version": delta3d_version,
            },
        }
        desired = parse_spec(specification).model_dump()
        if library in revisions:
            current = client.get(f"/api/revisions/{revisions[library]}").json()["spec"]
            if current == desired:
                continue
        response = client.post(
            f"/api/projects/{project_id}/designs",
            json={"spec": specification, "reason": f"WD615 part: {library}"},
        )
        if response.status_code == 429:
            time.sleep(5)
            response = client.post(
                f"/api/projects/{project_id}/designs",
                json={"spec": specification, "reason": f"WD615 part: {library}"},
            )
        response.raise_for_status()
        submission = response.json()
        pending.append((library, submission["job"]["id"], submission["revision"]["id"]))
        if len(pending) >= 3:
            name, job_id, revision_id = pending.pop(0)
            wait(client, job_id, 600)
            revisions[name] = revision_id
            print(f"  generated {name}")
    for name, job_id, revision_id in pending:
        wait(client, job_id, 600)
        revisions[name] = revision_id
        print(f"  generated {name}")
    return revisions


def catalog_number(item: dict, mapping: dict) -> str | None:
    for prefix, (number, _) in mapping["per_component"].items():
        if item["name"].startswith(prefix):
            return number
    entry = mapping["libraries"].get(item["library"])
    return entry[0] if entry else None


def sync_assembly(client, project_id, engine, revisions, mapping, name, angle) -> dict:
    components = []
    for item in layout.placements(engine, revisions, angle):
        component = {key: value for key, value in item.items() if key != "library"}
        component["catalog_part_no"] = catalog_number(item, mapping)
        components.append(component)
    definition = {
        "name": name,
        "components": components,
        "notes": f"Crank angle {angle:g}° (cylinder 1 firing TDC at 0°). Rigid placement of exact concept solids; valve springs, belts, hoses, wiring and fuel lines are not modelled.",
    }
    existing = {
        item["name"]: item for item in client.get(f"/api/projects/{project_id}/assemblies").json()
    }
    if name in existing:
        current = client.get(f"/api/assemblies/{existing[name]['id']}").json()
        response = client.put(
            f"/api/assemblies/{current['id']}",
            json={"definition": definition, "expected_version": current["version"]},
        )
    else:
        response = client.post(f"/api/projects/{project_id}/assemblies", json=definition)
    response.raise_for_status()
    assembly_id = response.json()["id"]
    build = client.post(f"/api/assemblies/{assembly_id}/build")
    build.raise_for_status()
    print(f"  building {name} ({len(components)} components)…")
    wait(client, build.json()["id"], 2400)
    return client.get(f"/api/assemblies/{assembly_id}").json()


def download(client: httpx.Client, artifact_id: str, target: Path) -> None:
    with client.stream("GET", f"/api/artifacts/{artifact_id}", timeout=300) as response:
        response.raise_for_status()
        with target.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)


def write_bom(bom: dict, mapping: dict, target_csv: Path) -> None:
    with target_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "status",
                "catalog_part_no",
                "catalog_name",
                "example_component",
                "quantity",
                "modelled_unit_mass_kg",
                "catalog_net_weight_kg",
                "model_to_catalog_mass_ratio",
                "unit_price",
                "currency",
                "line_price",
                "catalog_flags",
            ]
        )
        for line in bom["lines"]:
            catalog = line.get("catalog") or {}
            status = (
                "modelled+catalog"
                if catalog
                else (
                    "catalog number missing"
                    if line.get("catalog_missing")
                    else "modelled, no catalog match"
                )
            )
            writer.writerow(
                [
                    status,
                    line.get("catalog_part_no") or "",
                    catalog.get("name") or "",
                    line["example_name"],
                    line["quantity"],
                    round(line["unit_mass_kg"], 3),
                    catalog.get("net_weight_kg") or "",
                    round(line["mass_ratio_model_to_catalog"], 3)
                    if line.get("mass_ratio_model_to_catalog")
                    else "",
                    catalog.get("price") or "",
                    catalog.get("currency") or "",
                    line.get("line_price") or "",
                    ";".join(catalog.get("flags") or []),
                ]
            )
        for number, label, quantity in mapping["not_modelled"]:
            writer.writerow(
                [
                    "catalog only (not modelled)",
                    number,
                    label,
                    "",
                    quantity,
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("DELTA_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--skip-catalog", action="store_true")
    arguments = parser.parse_args()
    definition = json.loads((PROJECT / "engine" / "wd615.json").read_text(encoding="utf-8"))
    mapping = json.loads((PROJECT / "engine" / "catalog_map.json").read_text(encoding="utf-8"))
    engine = layout.InlineEngine.model_validate(definition["engine"])
    specs = layout.part_specs(engine)
    outputs = PROJECT / "outputs"
    outputs.mkdir(exist_ok=True)
    (outputs / "engine-summary.json").write_text(
        json.dumps(layout.summary(engine), indent=2, default=float), encoding="utf-8"
    )
    with httpx.Client(base_url=arguments.url, timeout=120, trust_env=False) as client:
        login(client)
        project_id = ensure_project(client)
        print(f"project {project_id}")
        if not arguments.skip_catalog:
            imported = import_catalog(client, project_id)
            (outputs / "catalog-import-report.json").write_text(
                json.dumps(imported["report"], indent=2), encoding="utf-8"
            )
            print(f"catalog: {imported['catalog_size']} part numbers")
        revisions = sync_parts(client, project_id, specs)
        print(f"{len(revisions)} library parts ready")
        results = []
        for name, angle in ASSEMBLIES:
            assembly = sync_assembly(client, project_id, engine, revisions, mapping, name, angle)
            report = assembly["properties"]
            tag = f"{int(angle):03d}deg"
            (outputs / f"assembly-report-{tag}.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
            artifacts = {item["kind"]: item["id"] for item in assembly["artifacts"]}
            if "assembly_step" in artifacts:
                download(client, artifacts["assembly_step"], outputs / f"WD615_engine_{tag}.step")
            results.append(
                {
                    "name": name,
                    "status": assembly["status"],
                    "components": report["component_count"],
                    "mass_kg": round(report["total_mass_kg"], 2),
                    "interferences": len(report["interferences"]),
                    "elapsed_s": round(report["elapsed_seconds"], 1),
                }
            )
            if angle == 0.0:
                bom = client.get(f"/api/assemblies/{assembly['id']}/bom").json()
                (outputs / "bom.json").write_text(json.dumps(bom, indent=2), encoding="utf-8")
                write_bom(bom, mapping, outputs / "bom.csv")
        (outputs / "build-summary.json").write_text(
            json.dumps({"project_id": project_id, "assemblies": results}, indent=2),
            encoding="utf-8",
        )
        for result in results:
            print(result)


if __name__ == "__main__":
    main()
