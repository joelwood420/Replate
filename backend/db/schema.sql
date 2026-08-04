-- Single source of truth for the Replate schema.
--
-- Applied locally by the dev setup and in Azure by infra/modules/sql-schema.bicep
-- (which pulls this file in verbatim via loadTextContent). Every statement is
-- guarded so the file is safe to re-run - the deployment script re-runs on every
-- deploy, and local dev re-applies it routinely.
--
-- Requires SQL Server 2025 / Azure SQL Database for the VECTOR type used by
-- CulinaryEmbeddings.

IF OBJECT_ID(N'dbo.Users', N'U') IS NULL
CREATE TABLE Users (
    UserId       UNIQUEIDENTIFIER PRIMARY KEY,
    Email        NVARCHAR(256) NULL,
    DisplayName  NVARCHAR(200) NULL,
    CreatedAt    DATETIME2 DEFAULT SYSUTCDATETIME()
);
GO

IF OBJECT_ID(N'dbo.Restaurants', N'U') IS NULL
CREATE TABLE Restaurants (
    RestaurantId      NVARCHAR(100) PRIMARY KEY,
    Name              NVARCHAR(200) NOT NULL,
    Address           NVARCHAR(300) NULL,
    Latitude          DECIMAL(9,6) NULL,
    Longitude         DECIMAL(9,6) NULL,
    MenuSourceUrl     NVARCHAR(500) NULL,
    MenuLastFetchedAt DATETIME2 NULL,
    CreatedAt         DATETIME2 DEFAULT SYSUTCDATETIME()
);
GO

IF OBJECT_ID(N'dbo.MenuItems', N'U') IS NULL
CREATE TABLE MenuItems (
    MenuItemId       UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    RestaurantId     NVARCHAR(100) NOT NULL FOREIGN KEY REFERENCES Restaurants(RestaurantId),
    ItemName         NVARCHAR(200) NOT NULL,
    ItemDescription  NVARCHAR(1000) NULL,
    Price            NVARCHAR(50) NULL,
    CreatedAt        DATETIME2 DEFAULT SYSUTCDATETIME()
);
GO

IF OBJECT_ID(N'dbo.Jobs', N'U') IS NULL
CREATE TABLE Jobs (
    JobId                UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    UserId               UNIQUEIDENTIFIER NOT NULL FOREIGN KEY REFERENCES Users(UserId),
    Status               NVARCHAR(20) NOT NULL,
    ImageBlobUrl         NVARCHAR(500) NOT NULL,
    Latitude             DECIMAL(9,6) NULL,
    Longitude            DECIMAL(9,6) NULL,
    SelectedRestaurantId NVARCHAR(100) NULL FOREIGN KEY REFERENCES Restaurants(RestaurantId),
    ErrorMessage         NVARCHAR(1000) NULL,
    IsSaved              BIT NOT NULL DEFAULT 0,
    CreatedAt            DATETIME2 DEFAULT SYSUTCDATETIME(),
    UpdatedAt            DATETIME2 DEFAULT SYSUTCDATETIME(),
    INDEX IX_Jobs_UserId (UserId, CreatedAt DESC)
);
GO

IF OBJECT_ID(N'dbo.JobRestaurantCandidates', N'U') IS NULL
CREATE TABLE JobRestaurantCandidates (
    JobId         UNIQUEIDENTIFIER NOT NULL FOREIGN KEY REFERENCES Jobs(JobId),
    RestaurantId  NVARCHAR(100) NOT NULL FOREIGN KEY REFERENCES Restaurants(RestaurantId),
    DistanceM     INT NULL,
    PRIMARY KEY (JobId, RestaurantId)
);
GO

IF OBJECT_ID(N'dbo.JobResults', N'U') IS NULL
CREATE TABLE JobResults (
    JobId                UNIQUEIDENTIFIER PRIMARY KEY FOREIGN KEY REFERENCES Jobs(JobId),
    DishName             NVARCHAR(200) NULL,
    Cuisine              NVARCHAR(100) NULL,
    Confidence           FLOAT NULL,
    MatchedRestaurantId  NVARCHAR(100) NULL FOREIGN KEY REFERENCES Restaurants(RestaurantId),
    MatchedMenuItemId    UNIQUEIDENTIFIER NULL FOREIGN KEY REFERENCES MenuItems(MenuItemId),
    MatchConfidence      FLOAT NULL,
    MatchMethod          NVARCHAR(30) NOT NULL,
    CreatedAt            DATETIME2 DEFAULT SYSUTCDATETIME()
);
GO

IF OBJECT_ID(N'dbo.DishElements', N'U') IS NULL
CREATE TABLE DishElements (
    ElementId    UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    JobId        UNIQUEIDENTIFIER NOT NULL FOREIGN KEY REFERENCES Jobs(JobId),
    Name         NVARCHAR(150) NOT NULL,
    Description  NVARCHAR(500) NULL,
    Role         NVARCHAR(50) NULL,
    SortOrder    INT NOT NULL
);
GO

IF OBJECT_ID(N'dbo.ElementIngredients', N'U') IS NULL
CREATE TABLE ElementIngredients (
    ElementId       UNIQUEIDENTIFIER NOT NULL FOREIGN KEY REFERENCES DishElements(ElementId),
    IngredientName  NVARCHAR(150) NOT NULL,
    Amount          NVARCHAR(50) NULL,
    Unit            NVARCHAR(20) NULL,
    SortOrder       INT NOT NULL,
    PRIMARY KEY (ElementId, SortOrder)
);
GO

IF OBJECT_ID(N'dbo.ElementSteps', N'U') IS NULL
CREATE TABLE ElementSteps (
    ElementId    UNIQUEIDENTIFIER NOT NULL FOREIGN KEY REFERENCES DishElements(ElementId),
    StepNumber   INT NOT NULL,
    Instruction  NVARCHAR(1000) NOT NULL,
    PRIMARY KEY (ElementId, StepNumber)
);
GO

IF OBJECT_ID(N'dbo.CulinaryEmbeddings', N'U') IS NULL
CREATE TABLE CulinaryEmbeddings (
    EmbeddingId  UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    SourceText   NVARCHAR(MAX) NOT NULL,
    Embedding    VECTOR(1536) NOT NULL,
    CuisineType  NVARCHAR(100) NULL,
    SourceUrl    NVARCHAR(500) NULL,
    CreatedAt    DATETIME2 DEFAULT SYSUTCDATETIME()
);
GO

-- Per-user call quotas (shared/rate_limit.py), capping AI spend from any single
-- user. One row per (user, action, hour): the hourly limit reads the current
-- bucket and the daily limit sums the last 24, so both windows are derived from
-- one bucket granularity rather than two counters that can drift out of step.
-- Rows older than the daily window are deleted on the owning user's next call.
IF OBJECT_ID(N'dbo.RateLimitCounters', N'U') IS NULL
CREATE TABLE RateLimitCounters (
    UserId       UNIQUEIDENTIFIER NOT NULL FOREIGN KEY REFERENCES Users(UserId),
    Action       NVARCHAR(30) NOT NULL,
    WindowStart  DATETIME2 NOT NULL,
    CallCount    INT NOT NULL,
    PRIMARY KEY (UserId, Action, WindowStart)
);
GO

-- ---------------------------------------------------------------------------
-- Additive column changes.
--
-- These live below the CREATE TABLE block rather than inside it on purpose.
-- Each CREATE TABLE above is wrapped in IF OBJECT_ID(...) IS NULL, so once a
-- table exists that whole statement is a no-op - editing a column into the
-- table body would silently do nothing on every database that already exists.
-- Adding columns therefore needs its own separately-guarded batch.
-- ---------------------------------------------------------------------------

-- Stage 1 of the pipeline (identify + menu match) persists the vision model's
-- raw guess so stage 2 (recipe generation, triggered later by the user pressing
-- "Reverse engineer") can use it as input. Before the pipeline was split, the
-- guess only ever survived as DishElements rows written by the generator.
IF COL_LENGTH('dbo.JobResults', 'VisionGuessJson') IS NULL
    ALTER TABLE JobResults ADD VisionGuessJson NVARCHAR(MAX) NULL;
GO
