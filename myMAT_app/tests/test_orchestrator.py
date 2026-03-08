from __future__ import annotations

import unittest

from myMAT_app.api.db.ops_store import MatOpsDbConfig, MatOpsStore
from myMAT_app.api.orchestrator import OrchestratorDeps, run_orchestrator


class TestOrchestrator(unittest.TestCase):
    def test_routes_customer_service_with_hint(self) -> None:
        deps = OrchestratorDeps(
            ops_store=MatOpsStore(
                MatOpsDbConfig(
                    enabled=False,
                    dsn=None,
                    host="127.0.0.1",
                    port=5432,
                    dbname="x",
                    user="x",
                    password="x",
                    sslmode="disable",
                    connect_timeout=1,
                )
            )
        )
        result = run_orchestrator(
            deps=deps,
            message="Need order ETA for ORD-20250301-1001",
            selected_agent_hint="agent_customer_service",
            chat_model="gpt-4.1-nano",
            retrieval=None,
            form_payload=None,
            history=None,
        )
        self.assertEqual(result["routed_agent"], "agent_customer_service")
        self.assertIn("sales", result["answer_text"].lower())

    def test_complaints_route_by_intent(self) -> None:
        deps = OrchestratorDeps(
            ops_store=MatOpsStore(
                MatOpsDbConfig(
                    enabled=False,
                    dsn=None,
                    host="127.0.0.1",
                    port=5432,
                    dbname="x",
                    user="x",
                    password="x",
                    sslmode="disable",
                    connect_timeout=1,
                )
            )
        )
        result = run_orchestrator(
            deps=deps,
            message="I want to open a complaint for defective parts",
            selected_agent_hint=None,
            chat_model="gpt-4.1-nano",
            retrieval=None,
            form_payload=None,
            history=None,
        )
        self.assertEqual(result["routed_agent"], "agent_complains_management")


if __name__ == "__main__":
    unittest.main()
