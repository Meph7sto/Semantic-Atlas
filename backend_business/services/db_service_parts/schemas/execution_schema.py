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
            graph_type TEXT NOT NULL CHECK (graph_type = 'execution_topology_template'),
            version INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL CHECK (status IN ('draft', 'active')) DEFAULT 'draft',
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
            node_type TEXT NOT NULL CHECK (node_type IN ('start', 'node', 'decision', 'handoff', 'end')),
            role_type TEXT NOT NULL CHECK (role_type IN ('human', 'agent', 'system')),
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
    cur.execute(
        """
        DO $$
        DECLARE
            old_constraint_name TEXT;
        BEGIN
            SELECT conname
              INTO old_constraint_name
              FROM pg_constraint
             WHERE conrelid = 'execution_nodes'::regclass
               AND contype = 'c'
               AND pg_get_constraintdef(oid) LIKE '%node_type%'
               AND pg_get_constraintdef(oid) LIKE '%task%';

            IF old_constraint_name IS NOT NULL THEN
                EXECUTE format('ALTER TABLE execution_nodes DROP CONSTRAINT %I', old_constraint_name);
                
                UPDATE execution_nodes SET node_type = 'node' WHERE node_type = 'task';
                
                ALTER TABLE execution_nodes
                ADD CONSTRAINT chk_execution_nodes_node_type
                CHECK (node_type IN ('start', 'node', 'decision', 'handoff', 'end'));
            END IF;
        END $$;
        """
    )
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
            edge_type TEXT NOT NULL CHECK (edge_type IN ('call', 'return', 'retry')),
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
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_edges_graph ON execution_edges(graph_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_edges_source ON execution_edges(source_node_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_edges_target ON execution_edges(target_node_id)"
    )
