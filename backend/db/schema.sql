CREATE TABLE Users (
    UserId       UNIQUEIDENTIFIER PRIMARY KEY,
    Email        NVARCHAR(256) NULL,
    DisplayName  NVARCHAR(200) NULL,
    CreatedAt    DATETIME2 DEFAULT SYSUTCDATETIME()
);

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

CREATE TABLE MenuItems (
    MenuItemId       UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    RestaurantId     NVARCHAR(100) NOT NULL FOREIGN KEY REFERENCES Restaurants(RestaurantId),
    ItemName         NVARCHAR(200) NOT NULL,
    ItemDescription  NVARCHAR(1000) NULL,
    Price            NVARCHAR(50) NULL,
    CreatedAt        DATETIME2 DEFAULT SYSUTCDATETIME()
);

CREATE TABLE Jobs (
    JobId        UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    UserId       UNIQUEIDENTIFIER NOT NULL FOREIGN KEY REFERENCES Users(UserId),
    Status       NVARCHAR(20) NOT NULL,
    ImageBlobUrl NVARCHAR(500) NOT NULL,
    Latitude     DECIMAL(9,6) NULL,
    Longitude    DECIMAL(9,6) NULL,
    ErrorMessage NVARCHAR(1000) NULL,
    CreatedAt    DATETIME2 DEFAULT SYSUTCDATETIME(),
    UpdatedAt    DATETIME2 DEFAULT SYSUTCDATETIME(),
    INDEX IX_Jobs_UserId (UserId, CreatedAt DESC)
);

CREATE TABLE JobRestaurantCandidates (
    JobId         UNIQUEIDENTIFIER NOT NULL FOREIGN KEY REFERENCES Jobs(JobId),
    RestaurantId  NVARCHAR(100) NOT NULL FOREIGN KEY REFERENCES Restaurants(RestaurantId),
    DistanceM     INT NULL,
    PRIMARY KEY (JobId, RestaurantId)
);

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

CREATE TABLE DishElements (
    ElementId    UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    JobId        UNIQUEIDENTIFIER NOT NULL FOREIGN KEY REFERENCES Jobs(JobId),
    Name         NVARCHAR(150) NOT NULL,
    Description  NVARCHAR(500) NULL,
    SortOrder    INT NOT NULL
);

CREATE TABLE ElementIngredients (
    ElementId       UNIQUEIDENTIFIER NOT NULL FOREIGN KEY REFERENCES DishElements(ElementId),
    IngredientName  NVARCHAR(150) NOT NULL,
    Amount          NVARCHAR(50) NULL,
    Unit            NVARCHAR(20) NULL,
    SortOrder       INT NOT NULL,
    PRIMARY KEY (ElementId, SortOrder)
);

CREATE TABLE ElementSteps (
    ElementId    UNIQUEIDENTIFIER NOT NULL FOREIGN KEY REFERENCES DishElements(ElementId),
    StepNumber   INT NOT NULL,
    Instruction  NVARCHAR(1000) NOT NULL,
    PRIMARY KEY (ElementId, StepNumber)
);

CREATE TABLE CulinaryEmbeddings (
    EmbeddingId  UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    SourceText   NVARCHAR(MAX) NOT NULL,
    Embedding    VECTOR(1536) NOT NULL,
    CuisineType  NVARCHAR(100) NULL,
    SourceUrl    NVARCHAR(500) NULL,
    CreatedAt    DATETIME2 DEFAULT SYSUTCDATETIME()
);