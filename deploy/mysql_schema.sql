-- Semantic-Atlas DOORS-style schema for MySQL 8.x (utf8mb4)
-- 用法（Navicat）：
-- 1) 创建一个连接后，执行本文件（建议在新建查询中整体执行）
-- 2) 如需自定义库名/字符集，可修改下方 CREATE DATABASE

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE DATABASE IF NOT EXISTS semantic_atlas
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;

USE semantic_atlas;

-- -----------------------------
-- Project / Tenant
-- -----------------------------
CREATE TABLE IF NOT EXISTS project (
  id            CHAR(36)     NOT NULL,
  name          VARCHAR(128) NOT NULL,
  description   TEXT         NULL,
  created_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_project_name (name)
) ENGINE=InnoDB;

-- -----------------------------
-- Artifacts & transcripts (evidence as first-class citizen)
-- -----------------------------
CREATE TABLE IF NOT EXISTS artifact (
  id          CHAR(36)      NOT NULL,
  project_id  CHAR(36)      NOT NULL,
  type        VARCHAR(32)   NOT NULL,       -- video/audio/doc/text
  uri         TEXT          NULL,
  metadata    JSON          NULL,
  created_at  DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_artifact_project (project_id),
  CONSTRAINT fk_artifact_project FOREIGN KEY (project_id) REFERENCES project(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS transcript_segment (
  id          CHAR(36)      NOT NULL,
  artifact_id CHAR(36)      NOT NULL,
  start_ms    BIGINT        NULL,
  end_ms      BIGINT        NULL,
  speaker     VARCHAR(128)  NULL,
  text        TEXT          NOT NULL,
  embedding   JSON          NULL,           -- 可选：向量可放 json 或迁移到向量库
  metadata    JSON          NULL,
  created_at  DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_segment_artifact_time (artifact_id, start_ms, end_ms),
  FULLTEXT KEY ft_segment_text (text),
  CONSTRAINT fk_segment_artifact FOREIGN KEY (artifact_id) REFERENCES artifact(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS extraction_run (
  id            CHAR(36)     NOT NULL,
  artifact_id   CHAR(36)     NOT NULL,
  model         VARCHAR(128) NOT NULL,
  prompt_version VARCHAR(64) NULL,
  status        VARCHAR(32)  NOT NULL DEFAULT 'success', -- running/success/failed
  config        JSON         NULL,
  created_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_extract_artifact (artifact_id),
  CONSTRAINT fk_extract_artifact FOREIGN KEY (artifact_id) REFERENCES artifact(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS candidate_requirement (
  id               CHAR(36)     NOT NULL,
  extraction_run_id CHAR(36)     NOT NULL,
  text             TEXT         NOT NULL,
  confidence       DOUBLE       NULL,
  suggested_type   VARCHAR(64)  NULL,
  metadata         JSON         NULL,
  created_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_candidate_run (extraction_run_id),
  FULLTEXT KEY ft_candidate_text (text),
  CONSTRAINT fk_candidate_run FOREIGN KEY (extraction_run_id) REFERENCES extraction_run(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS candidate_evidence (
  candidate_id          CHAR(36)    NOT NULL,
  transcript_segment_id CHAR(36)    NOT NULL,
  score                 DOUBLE      NULL,
  span_offsets          JSON        NULL,
  created_at            DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (candidate_id, transcript_segment_id),
  KEY idx_cand_ev_segment (transcript_segment_id),
  CONSTRAINT fk_cand_ev_candidate FOREIGN KEY (candidate_id) REFERENCES candidate_requirement(id),
  CONSTRAINT fk_cand_ev_segment FOREIGN KEY (transcript_segment_id) REFERENCES transcript_segment(id)
) ENGINE=InnoDB;

-- -----------------------------
-- Requirement Object Library (DOORS Object + Revision)
-- -----------------------------
CREATE TABLE IF NOT EXISTS requirement_object (
  id             CHAR(36)     NOT NULL,
  project_id     CHAR(36)     NOT NULL,
  current_rev_id CHAR(36)     NULL,
  object_type    VARCHAR(64)  NOT NULL, -- business/stakeholder/system/software/test...
  object_key     VARCHAR(64)  NOT NULL, -- 去重键：如 sha256(normalized_text)
  created_by     VARCHAR(128) NULL,
  created_at     DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  deleted_at     DATETIME(3)  NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_req_obj_key (project_id, object_key),
  KEY idx_req_obj_project (project_id),
  CONSTRAINT fk_req_obj_project FOREIGN KEY (project_id) REFERENCES project(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS requirement_revision (
  id             CHAR(36)     NOT NULL,
  object_id      CHAR(36)     NOT NULL,
  rev_no         INT          NOT NULL,
  title          VARCHAR(256) NULL,
  text           MEDIUMTEXT   NOT NULL,
  rationale      TEXT         NULL,
  status         VARCHAR(32)  NOT NULL DEFAULT 'Proposed', -- Draft/Proposed/Accepted/Implemented/Verified/Deprecated
  source_kind    VARCHAR(32)  NOT NULL DEFAULT 'extracted', -- manual/imported/extracted
  quality_metrics JSON        NULL,
  created_by     VARCHAR(128) NULL,
  created_at     DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_req_rev_no (object_id, rev_no),
  FULLTEXT KEY ft_req_rev_text (text),
  CONSTRAINT fk_req_rev_obj FOREIGN KEY (object_id) REFERENCES requirement_object(id)
) ENGINE=InnoDB;

ALTER TABLE requirement_object
  ADD CONSTRAINT fk_req_obj_current_rev FOREIGN KEY (current_rev_id) REFERENCES requirement_revision(id);

CREATE TABLE IF NOT EXISTS evidence_link (
  id                  CHAR(36)    NOT NULL,
  rev_id              CHAR(36)    NOT NULL,
  transcript_segment_id CHAR(36)  NOT NULL,
  start_ms            BIGINT      NULL,
  end_ms              BIGINT      NULL,
  quote_text          VARCHAR(512) NULL,
  score               DOUBLE      NULL,
  created_at          DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_ev_rev (rev_id),
  KEY idx_ev_seg (transcript_segment_id),
  CONSTRAINT fk_ev_rev FOREIGN KEY (rev_id) REFERENCES requirement_revision(id),
  CONSTRAINT fk_ev_seg FOREIGN KEY (transcript_segment_id) REFERENCES transcript_segment(id)
) ENGINE=InnoDB;

-- -----------------------------
-- Links (trace/decompose/conflict/duplicate/depends_on...) + Link revisions for validation
-- -----------------------------
CREATE TABLE IF NOT EXISTS requirement_link (
  id             CHAR(36)     NOT NULL,
  project_id     CHAR(36)     NOT NULL,
  src_object_id  CHAR(36)     NOT NULL,
  dst_object_id  CHAR(36)     NOT NULL,
  link_type      VARCHAR(32)  NOT NULL, -- decompose/refine/conflict/duplicate/depends_on/implementation/support/...
  current_rev_id CHAR(36)     NULL,
  created_by     VARCHAR(128) NULL,
  created_at     DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_link_project (project_id),
  KEY idx_link_src (src_object_id),
  KEY idx_link_dst (dst_object_id),
  CONSTRAINT fk_link_project FOREIGN KEY (project_id) REFERENCES project(id),
  CONSTRAINT fk_link_src FOREIGN KEY (src_object_id) REFERENCES requirement_object(id),
  CONSTRAINT fk_link_dst FOREIGN KEY (dst_object_id) REFERENCES requirement_object(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS link_revision (
  id                CHAR(36)     NOT NULL,
  link_id           CHAR(36)     NOT NULL,
  rev_no            INT          NOT NULL,
  confidence        DOUBLE       NULL,
  validation_status VARCHAR(32)  NOT NULL DEFAULT 'proposed', -- proposed/accepted/rejected/needs_review
  validation_by     VARCHAR(128) NULL,
  validation_at     DATETIME(3)  NULL,
  comment           TEXT         NULL,
  evidence          JSON         NULL, -- 分析详情/raw_response/证据等
  created_by        VARCHAR(128) NULL,
  created_at        DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_link_rev_no (link_id, rev_no),
  KEY idx_link_rev_status (validation_status),
  CONSTRAINT fk_link_rev_link FOREIGN KEY (link_id) REFERENCES requirement_link(id)
) ENGINE=InnoDB;

ALTER TABLE requirement_link
  ADD CONSTRAINT fk_link_current_rev FOREIGN KEY (current_rev_id) REFERENCES link_revision(id);

-- -----------------------------
-- Workspace / analysis runs
-- -----------------------------
CREATE TABLE IF NOT EXISTS workspace (
  id          CHAR(36)    NOT NULL,
  project_id  CHAR(36)    NOT NULL,
  scope_query JSON        NULL,
  created_by  VARCHAR(128) NULL,
  created_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_ws_project (project_id),
  CONSTRAINT fk_ws_project FOREIGN KEY (project_id) REFERENCES project(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS analysis_run (
  id           CHAR(36)    NOT NULL,
  workspace_id CHAR(36)    NOT NULL,
  stage        VARCHAR(32) NOT NULL, -- trace/conflict/classify/acquisition
  config       JSON        NULL,
  status       VARCHAR(32) NOT NULL DEFAULT 'success',
  created_at   DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_run_ws (workspace_id),
  CONSTRAINT fk_run_ws FOREIGN KEY (workspace_id) REFERENCES workspace(id)
) ENGINE=InnoDB;

-- 冲突与分类作为“分析结果”
CREATE TABLE IF NOT EXISTS conflict_finding (
  id            CHAR(36)    NOT NULL,
  run_id        CHAR(36)    NOT NULL,
  object_a_id   CHAR(36)    NOT NULL,
  object_b_id   CHAR(36)    NOT NULL,
  conflict_type VARCHAR(64) NULL,
  severity      VARCHAR(16) NULL,
  explanation   TEXT        NULL,
  status        VARCHAR(32) NOT NULL DEFAULT 'open', -- open/accepted/resolved
  created_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_conflict_run (run_id),
  CONSTRAINT fk_conflict_run FOREIGN KEY (run_id) REFERENCES analysis_run(id),
  CONSTRAINT fk_conflict_a FOREIGN KEY (object_a_id) REFERENCES requirement_object(id),
  CONSTRAINT fk_conflict_b FOREIGN KEY (object_b_id) REFERENCES requirement_object(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS classification_result (
  id         CHAR(36)    NOT NULL,
  run_id     CHAR(36)    NOT NULL,
  object_id  CHAR(36)    NOT NULL,
  label      VARCHAR(64) NOT NULL,
  score      DOUBLE      NULL,
  rationale  TEXT        NULL,
  status     VARCHAR(32) NOT NULL DEFAULT 'proposed', -- proposed/accepted/rejected
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_class_run (run_id),
  KEY idx_class_obj (object_id),
  CONSTRAINT fk_class_run FOREIGN KEY (run_id) REFERENCES analysis_run(id),
  CONSTRAINT fk_class_obj FOREIGN KEY (object_id) REFERENCES requirement_object(id)
) ENGINE=InnoDB;

-- -----------------------------
-- Module / View (DOORS Module)
-- -----------------------------
CREATE TABLE IF NOT EXISTS module (
  id          CHAR(36)     NOT NULL,
  project_id  CHAR(36)     NOT NULL,
  name        VARCHAR(128) NOT NULL,
  description TEXT         NULL,
  created_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_module_name (project_id, name),
  CONSTRAINT fk_module_project FOREIGN KEY (project_id) REFERENCES project(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS module_object (
  module_id     CHAR(36)   NOT NULL,
  object_id     CHAR(36)   NOT NULL,
  position      INT        NOT NULL,
  outline_level INT        NOT NULL DEFAULT 1,
  PRIMARY KEY (module_id, object_id),
  KEY idx_mod_obj_pos (module_id, position),
  CONSTRAINT fk_mod_obj_module FOREIGN KEY (module_id) REFERENCES module(id),
  CONSTRAINT fk_mod_obj_object FOREIGN KEY (object_id) REFERENCES requirement_object(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS module_baseline (
  id         CHAR(36)     NOT NULL,
  module_id  CHAR(36)     NOT NULL,
  name       VARCHAR(128) NOT NULL,
  created_by VARCHAR(128) NULL,
  created_at DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_baseline_module (module_id),
  CONSTRAINT fk_baseline_module FOREIGN KEY (module_id) REFERENCES module(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS baseline_item (
  baseline_id CHAR(36) NOT NULL,
  object_id   CHAR(36) NOT NULL,
  rev_id      CHAR(36) NOT NULL,
  PRIMARY KEY (baseline_id, object_id),
  CONSTRAINT fk_bi_baseline FOREIGN KEY (baseline_id) REFERENCES module_baseline(id),
  CONSTRAINT fk_bi_object FOREIGN KEY (object_id) REFERENCES requirement_object(id),
  CONSTRAINT fk_bi_rev FOREIGN KEY (rev_id) REFERENCES requirement_revision(id)
) ENGINE=InnoDB;

-- -----------------------------
-- Attribute system (DOORS Attributes)
-- -----------------------------
CREATE TABLE IF NOT EXISTS attribute_def (
  id              CHAR(36)     NOT NULL,
  project_id      CHAR(36)     NOT NULL,
  name            VARCHAR(128) NOT NULL,
  scope           VARCHAR(16)  NOT NULL DEFAULT 'rev', -- object/rev
  type            VARCHAR(16)  NOT NULL,               -- string/int/float/bool/date/enum/json/richtext
  required        TINYINT(1)   NOT NULL DEFAULT 0,
  default_value   JSON         NULL,
  enum_values     JSON         NULL,
  validation_rule JSON         NULL,
  created_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_attr_name (project_id, name),
  CONSTRAINT fk_attr_project FOREIGN KEY (project_id) REFERENCES project(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS attribute_value (
  id               CHAR(36)     NOT NULL,
  attribute_def_id CHAR(36)     NOT NULL,
  object_id        CHAR(36)     NULL,
  rev_id           CHAR(36)     NULL,
  value_string     VARCHAR(1024) NULL,
  value_int        BIGINT       NULL,
  value_float      DOUBLE       NULL,
  value_bool       TINYINT(1)   NULL,
  value_date       DATETIME(3)  NULL,
  value_json       JSON         NULL,
  created_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_attr_obj (object_id),
  KEY idx_attr_rev (rev_id),
  CONSTRAINT fk_attr_val_def FOREIGN KEY (attribute_def_id) REFERENCES attribute_def(id),
  CONSTRAINT fk_attr_val_obj FOREIGN KEY (object_id) REFERENCES requirement_object(id),
  CONSTRAINT fk_attr_val_rev FOREIGN KEY (rev_id) REFERENCES requirement_revision(id)
) ENGINE=InnoDB;

SET FOREIGN_KEY_CHECKS = 1;