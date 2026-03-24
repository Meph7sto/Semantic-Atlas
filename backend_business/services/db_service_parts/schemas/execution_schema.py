def init_execution_schema(cur):
    # ========================
    # Execution Topology Tables
    # ========================

    # execution_graphs: 执行拓扑图模板
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_graphs (
            graph_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES manage_projects(project_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            graph_type TEXT NOT NULL CHECK (
                graph_type IN ('execution_topology_template', 'agent_runtime_execution')
            ),
            version INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL CHECK (
                status IN ('draft', 'active', 'running', 'succeeded', 'failed', 'suspended')
            ) DEFAULT 'draft',
            layout_json JSONB,
            meta_json JSONB,
            created_by TEXT,
            updated_by TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_graphs_project ON execution_graphs(project_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_graphs_status ON execution_graphs(status)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_graphs_type ON execution_graphs(graph_type)"
    )

    cur.execute(
        """
        DO $$
        DECLARE
            graph_type_constraint_name TEXT;
            status_constraint_name TEXT;
        BEGIN
            IF EXISTS (
                SELECT 1
                  FROM pg_constraint
                 WHERE conrelid = 'execution_graphs'::regclass
                   AND contype = 'c'
                   AND pg_get_constraintdef(oid) ILIKE '%graph_type%'
                   AND (
                        conname <> 'chk_execution_graphs_graph_type'
                        OR pg_get_constraintdef(oid) NOT LIKE '%execution_topology_template%'
                        OR pg_get_constraintdef(oid) NOT LIKE '%agent_runtime_execution%'
                   )
            ) OR NOT EXISTS (
                SELECT 1
                  FROM pg_constraint
                 WHERE conrelid = 'execution_graphs'::regclass
                   AND contype = 'c'
                   AND conname = 'chk_execution_graphs_graph_type'
            ) THEN
                FOR graph_type_constraint_name IN
                    SELECT conname
                      FROM pg_constraint
                     WHERE conrelid = 'execution_graphs'::regclass
                       AND contype = 'c'
                       AND pg_get_constraintdef(oid) ILIKE '%graph_type%'
                LOOP
                    EXECUTE format('ALTER TABLE execution_graphs DROP CONSTRAINT %I', graph_type_constraint_name);
                END LOOP;
                ALTER TABLE execution_graphs
                ADD CONSTRAINT chk_execution_graphs_graph_type
                CHECK (graph_type IN ('execution_topology_template', 'agent_runtime_execution'));
            END IF;

            IF EXISTS (
                SELECT 1
                  FROM pg_constraint
                 WHERE conrelid = 'execution_graphs'::regclass
                   AND contype = 'c'
                   AND pg_get_constraintdef(oid) ILIKE '%status%'
                   AND (
                        conname <> 'chk_execution_graphs_status'
                        OR pg_get_constraintdef(oid) NOT LIKE '%draft%'
                        OR pg_get_constraintdef(oid) NOT LIKE '%active%'
                        OR pg_get_constraintdef(oid) NOT LIKE '%running%'
                        OR pg_get_constraintdef(oid) NOT LIKE '%succeeded%'
                        OR pg_get_constraintdef(oid) NOT LIKE '%failed%'
                        OR pg_get_constraintdef(oid) NOT LIKE '%suspended%'
                   )
            ) OR NOT EXISTS (
                SELECT 1
                  FROM pg_constraint
                 WHERE conrelid = 'execution_graphs'::regclass
                   AND contype = 'c'
                   AND conname = 'chk_execution_graphs_status'
            ) THEN
                FOR status_constraint_name IN
                    SELECT conname
                      FROM pg_constraint
                     WHERE conrelid = 'execution_graphs'::regclass
                       AND contype = 'c'
                       AND pg_get_constraintdef(oid) ILIKE '%status%'
                LOOP
                    EXECUTE format('ALTER TABLE execution_graphs DROP CONSTRAINT %I', status_constraint_name);
                END LOOP;
                ALTER TABLE execution_graphs
                ADD CONSTRAINT chk_execution_graphs_status
                CHECK (status IN ('draft', 'active', 'running', 'succeeded', 'failed', 'suspended'));
            END IF;
        END $$;
        """
    )

    # execution_containers: 执行拓扑容器（容器包含多个节点）
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_containers (
            container_id TEXT PRIMARY KEY,
            graph_id TEXT NOT NULL REFERENCES execution_graphs(graph_id) ON DELETE CASCADE,
            container_key TEXT NOT NULL,
            label TEXT NOT NULL,
            role_type TEXT NOT NULL CHECK (role_type IN ('human', 'agent', 'system')),
            config_json JSONB,
            order_index INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            UNIQUE(graph_id, container_key)
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_containers_graph ON execution_containers(graph_id)"
    )

    # execution_nodes: 执行拓扑节点
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_nodes (
            node_id TEXT PRIMARY KEY,
            graph_id TEXT NOT NULL REFERENCES execution_graphs(graph_id) ON DELETE CASCADE,
            container_id TEXT REFERENCES execution_containers(container_id) ON DELETE SET NULL,
            node_key TEXT NOT NULL,
            label TEXT NOT NULL,
            node_type TEXT NOT NULL CHECK (
                node_type IN ('start', 'llm', 'handoff', 'invoke', 'end')
            ),
            role_type TEXT NOT NULL CHECK (role_type IN ('human', 'agent', 'system')),
            phase_label TEXT,
            task_prompt TEXT,
            conditional_edges JSONB,
            config_json JSONB,
            input_schema_json JSONB,
            output_schema_json JSONB,
            order_index INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            UNIQUE(graph_id, node_key)
        )
        """
    )
    # Migration: unify node types to 5 kinds (start/llm/handoff/invoke/end).
    # Migrate legacy 'node', 'decision', 'task' → 'llm' and replace the CHECK constraint.
    cur.execute(
        """
        DO $$
        DECLARE
            constraint_name TEXT;
            has_unified_constraint BOOLEAN;
        BEGIN
            -- Check whether the unified 5-type constraint already exists.
            SELECT EXISTS (
                SELECT 1
                  FROM pg_constraint
                 WHERE conrelid = 'execution_nodes'::regclass
                   AND contype = 'c'
                   AND conname = 'chk_execution_nodes_node_type'
                   AND pg_get_constraintdef(oid) ILIKE '%node_type%'
                   AND pg_get_constraintdef(oid) NOT ILIKE '%decision%'
                   AND pg_get_constraintdef(oid) NOT ILIKE '%''node''%'
            ) INTO has_unified_constraint;

            IF NOT has_unified_constraint THEN
                -- Drop ALL existing node_type CHECK constraints.
                FOR constraint_name IN
                    SELECT conname
                      FROM pg_constraint
                     WHERE conrelid = 'execution_nodes'::regclass
                       AND contype = 'c'
                       AND pg_get_constraintdef(oid) ILIKE '%node_type%'
                LOOP
                    EXECUTE format('ALTER TABLE execution_nodes DROP CONSTRAINT %I', constraint_name);
                END LOOP;

                -- Keep the legacy two-step rewrite visible for older migration checks.
                UPDATE execution_nodes SET node_type = 'node' WHERE node_type = 'task';
                UPDATE execution_nodes SET node_type = 'llm' WHERE node_type IN ('node', 'decision');

                -- Add the unified 5-type constraint.
                ALTER TABLE execution_nodes
                ADD CONSTRAINT chk_execution_nodes_node_type
                CHECK (node_type IN ('start', 'llm', 'handoff', 'invoke', 'end'));
            END IF;
        END $$;
        """
    )
    # Migration: add phase_label / task_prompt / conditional_edges columns.
    cur.execute("ALTER TABLE execution_nodes ADD COLUMN IF NOT EXISTS phase_label TEXT")
    cur.execute("ALTER TABLE execution_nodes ADD COLUMN IF NOT EXISTS task_prompt TEXT")
    cur.execute("ALTER TABLE execution_nodes ADD COLUMN IF NOT EXISTS conditional_edges JSONB")
    cur.execute(
        "ALTER TABLE execution_nodes ADD COLUMN IF NOT EXISTS container_id TEXT"
    )
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_execution_nodes_container'
            ) THEN
                ALTER TABLE execution_nodes
                ADD CONSTRAINT fk_execution_nodes_container
                FOREIGN KEY (container_id)
                REFERENCES execution_containers(container_id)
                ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_nodes_graph ON execution_nodes(graph_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_nodes_container ON execution_nodes(container_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_nodes_type ON execution_nodes(node_type)"
    )

    # execution_edges: 执行拓扑边
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_edges (
            edge_id TEXT PRIMARY KEY,
            graph_id TEXT NOT NULL REFERENCES execution_graphs(graph_id) ON DELETE CASCADE,
            source_node_id TEXT NOT NULL REFERENCES execution_nodes(node_id) ON DELETE CASCADE,
            target_node_id TEXT NOT NULL REFERENCES execution_nodes(node_id) ON DELETE CASCADE,
            edge_type TEXT NOT NULL CHECK (edge_type IN ('seq', 'call', 'return', 'retry')),
            label TEXT,
            condition_expr TEXT,
            config_json JSONB,
            order_index INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            UNIQUE(graph_id, source_node_id, target_node_id, edge_type)
        )
        """
    )
    # Migration: ensure edge_type CHECK constraint includes 'seq'
    cur.execute(
        """
        DO $$
        DECLARE
            constraint_name TEXT;
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                  FROM pg_constraint
                 WHERE conrelid = 'execution_edges'::regclass
                   AND contype = 'c'
                   AND conname = 'chk_execution_edges_edge_type'
                   AND pg_get_constraintdef(oid) ILIKE '%seq%'
            ) THEN
                -- Drop ALL existing edge_type CHECK constraints.
                FOR constraint_name IN
                    SELECT conname
                      FROM pg_constraint
                     WHERE conrelid = 'execution_edges'::regclass
                       AND contype = 'c'
                       AND pg_get_constraintdef(oid) ILIKE '%edge_type%'
                LOOP
                    EXECUTE format('ALTER TABLE execution_edges DROP CONSTRAINT %I', constraint_name);
                END LOOP;
                ALTER TABLE execution_edges
                ADD CONSTRAINT chk_execution_edges_edge_type
                CHECK (edge_type IN ('seq', 'call', 'return', 'retry'));
            END IF;
        END $$;
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_edges_graph ON execution_edges(graph_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_edges_source ON execution_edges(source_node_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_edges_target ON execution_edges(target_node_id)"
    )

    # execution_subgraphs: 子图（container 的子元素，对应拓扑图中一个可见节点）
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_subgraphs (
            subgraph_id TEXT PRIMARY KEY,
            graph_id TEXT NOT NULL REFERENCES execution_graphs(graph_id) ON DELETE CASCADE,
            container_id TEXT NOT NULL REFERENCES execution_containers(container_id) ON DELETE CASCADE,
            subgraph_key TEXT NOT NULL,
            label TEXT NOT NULL,
            task_description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'completed', 'failed')),
            order_index INTEGER NOT NULL DEFAULT 0,
            config_json JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            UNIQUE(graph_id, subgraph_key)
        )
        """
    )
    # Migration: add status column to existing execution_subgraphs table
    cur.execute(
        "ALTER TABLE execution_subgraphs ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'pending'"
    )
    cur.execute(
        """
        DO $$
        DECLARE
            constraint_name TEXT;
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                  FROM pg_constraint
                 WHERE conrelid = 'execution_subgraphs'::regclass
                   AND contype = 'c'
                   AND conname = 'chk_execution_subgraphs_status'
            ) THEN
                -- Drop any existing status CHECK constraints first.
                FOR constraint_name IN
                    SELECT conname
                      FROM pg_constraint
                     WHERE conrelid = 'execution_subgraphs'::regclass
                       AND contype = 'c'
                       AND pg_get_constraintdef(oid) ILIKE '%status%'
                LOOP
                    EXECUTE format('ALTER TABLE execution_subgraphs DROP CONSTRAINT %I', constraint_name);
                END LOOP;
                ALTER TABLE execution_subgraphs
                ADD CONSTRAINT chk_execution_subgraphs_status
                CHECK (status IN ('pending', 'running', 'completed', 'failed'));
            END IF;
        END $$;
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_subgraphs_graph ON execution_subgraphs(graph_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_subgraphs_container ON execution_subgraphs(container_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_subgraphs_status ON execution_subgraphs(status)"
    )

    # Migration: add subgraph_id column to execution_nodes (nullable for backward compat)
    cur.execute(
        "ALTER TABLE execution_nodes ADD COLUMN IF NOT EXISTS subgraph_id TEXT"
    )
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_execution_nodes_subgraph'
            ) THEN
                ALTER TABLE execution_nodes
                ADD CONSTRAINT fk_execution_nodes_subgraph
                FOREIGN KEY (subgraph_id)
                REFERENCES execution_subgraphs(subgraph_id)
                ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_nodes_subgraph ON execution_nodes(subgraph_id)"
    )
