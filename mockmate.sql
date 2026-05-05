-- MockMate 数据库初始化脚本
-- 使用方式：mysql -u root -p < mockmate.sql

CREATE DATABASE IF NOT EXISTS mockmate
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE mockmate;

-- ==================== 面试会话表 ====================
CREATE TABLE IF NOT EXISTS sessions (
    id               VARCHAR(12)    PRIMARY KEY COMMENT '会话ID（UUID前12位）',
    position         VARCHAR(255)   DEFAULT ''  COMMENT '目标岗位',
    company          VARCHAR(255)   DEFAULT ''  COMMENT '目标公司',
    round            VARCHAR(20)    DEFAULT ''  COMMENT '面试轮次(written/tech_1/tech_2/comprehensive)',
    resume           LONGTEXT                   COMMENT '简历内容',
    profile          JSON                       COMMENT '岗位画像JSON',
    history          JSON                       COMMENT '问答历史记录JSON',
    report           JSON                       COMMENT '面试报告JSON',
    current_question JSON                       COMMENT '当前题目JSON',
    current_index    INT            DEFAULT 0   COMMENT '当前题目索引',
    created_at       DATETIME       DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at       DATETIME       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='面试会话表';

-- ==================== 岗位研究缓存表 ====================
CREATE TABLE IF NOT EXISTS research_cache (
    position     VARCHAR(255) PRIMARY KEY      COMMENT '岗位名称（主键）',
    data         JSON                          COMMENT '岗位画像JSON数据',
    summary      VARCHAR(500) DEFAULT ''       COMMENT '岗位简介摘要',
    skill_count  INT          DEFAULT 0        COMMENT '技能数量',
    topic_count  INT          DEFAULT 0        COMMENT '面试话题数量',
    expires_at   DATETIME                      COMMENT '缓存过期时间',
    cached_at    DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '缓存时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='岗位研究缓存表';

-- ==================== 搜索历史表 ====================
CREATE TABLE IF NOT EXISTS search_history (
    id           INT            AUTO_INCREMENT PRIMARY KEY COMMENT '自增ID',
    position     VARCHAR(255)   NOT NULL       COMMENT '搜索的岗位名称',
    summary      VARCHAR(500)   DEFAULT ''     COMMENT '搜索结果摘要',
    skill_count  INT            DEFAULT 0      COMMENT '技能数量',
    topic_count  INT            DEFAULT 0      COMMENT '话题数量',
    tech_stack   JSON                          COMMENT '技术栈JSON',
    created_at   DATETIME       DEFAULT CURRENT_TIMESTAMP COMMENT '搜索时间',
    INDEX idx_position (position),
    INDEX idx_created  (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='岗位搜索历史表';

-- ==================== 题目收藏表 ====================
CREATE TABLE IF NOT EXISTS favorites (
    id             INT            AUTO_INCREMENT PRIMARY KEY COMMENT '自增ID',
    session_id     VARCHAR(12)    DEFAULT ''     COMMENT '来源会话ID',
    question       TEXT           NOT NULL       COMMENT '题目内容',
    type           VARCHAR(20)    DEFAULT ''     COMMENT '题目类型(技术/行为/设计)',
    difficulty     VARCHAR(10)    DEFAULT ''     COMMENT '难度(easy/medium/hard)',
    topic          VARCHAR(100)   DEFAULT ''     COMMENT '主题',
    user_answer    TEXT                          COMMENT '用户的回答',
    overall_score  INT            DEFAULT 0      COMMENT '综合得分',
    notes          TEXT                          COMMENT '备注',
    saved_at       DATETIME       DEFAULT CURRENT_TIMESTAMP COMMENT '收藏时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='题目收藏表';

-- ==================== 自定义题目表 ====================
CREATE TABLE IF NOT EXISTS custom_questions (
    id               INT            AUTO_INCREMENT PRIMARY KEY COMMENT '自增ID',
    question         TEXT           NOT NULL       COMMENT '题目内容',
    type             VARCHAR(20)    DEFAULT '技术'  COMMENT '题目类型(技术/行为/设计/项目)',
    difficulty       VARCHAR(10)    DEFAULT 'medium' COMMENT '难度(easy/medium/hard)',
    topic            VARCHAR(100)   DEFAULT ''     COMMENT '主题',
    expected_points  JSON                          COMMENT '考察要点JSON',
    tags             VARCHAR(200)   DEFAULT ''     COMMENT '标签(逗号分隔)',
    created_at       DATETIME       DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at       DATETIME       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='自定义题目表';
