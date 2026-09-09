/*
    Seed-LabData.sql
    ----------------
    Inflates a lab database to :TargetGb using one of three data shapes.

    The shape matters because the cost model assumes fixed compression ratios
    (BACPAC ~4x, native backup ~3x). Those ratios are entirely data-dependent, so the
    lab generates deliberate best and worst cases to bracket the real range:

      compressible : long runs of repeated bytes. Compresses extremely well. Upper bound.
      random       : CRYPT_GEN_RANDOM output. Essentially incompressible. Lower bound.
      mixed        : realistic blend of narrow typed columns and moderately repetitive
                     text. Used for the size-calibration databases so the fitted
                     minutes-per-GB slope reflects something plausible.

    Variables (passed via Invoke-Sqlcmd -Variable):
      TargetGb : target size of the data rows, in GB
      Shape    : compressible | random | mixed
*/

SET NOCOUNT ON;
GO

DECLARE @TargetGb int = CAST('$(TargetGb)' AS int);
DECLARE @Shape    nvarchar(20) = N'$(Shape)';

IF @Shape NOT IN (N'compressible', N'random', N'mixed')
    THROW 50001, 'Shape must be compressible, random or mixed.', 1;

IF OBJECT_ID('dbo.LabPayload', 'U') IS NOT NULL DROP TABLE dbo.LabPayload;

/*
    ROW compression is explicitly disabled. The point of the probe databases is to
    measure how the BACKUP/BACPAC layer compresses the data, so letting the storage
    engine pre-compress it first would confound the measurement.
*/
CREATE TABLE dbo.LabPayload
(
    Id          bigint IDENTITY(1,1) NOT NULL,
    CreatedUtc  datetime2(3)   NOT NULL CONSTRAINT DF_LabPayload_Created DEFAULT SYSUTCDATETIME(),
    Category    int            NOT NULL,
    Amount      decimal(18,4)  NOT NULL,
    Payload     varbinary(8000) NOT NULL,
    CONSTRAINT PK_LabPayload PRIMARY KEY CLUSTERED (Id)
) WITH (DATA_COMPRESSION = NONE);
GO

DECLARE @TargetGb int = CAST('$(TargetGb)' AS int);
DECLARE @Shape    nvarchar(20) = N'$(Shape)';

/* Each row carries ~8 KB of payload, so ~131,072 rows per GB. */
DECLARE @RowsPerGb   bigint = 131072;
DECLARE @TargetRows  bigint = @RowsPerGb * @TargetGb;
DECLARE @BatchRows   int    = 2000;      -- keeps the transaction log bounded
DECLARE @Inserted    bigint = 0;
DECLARE @StartUtc    datetime2 = SYSUTCDATETIME();

WHILE @Inserted < @TargetRows
BEGIN
    DECLARE @ThisBatch int =
        CASE WHEN @TargetRows - @Inserted < @BatchRows
             THEN CAST(@TargetRows - @Inserted AS int)
             ELSE @BatchRows END;

    /*
        A tally derived from system catalogs avoids a helper table and is plenty fast
        at these batch sizes.
    */
    ;WITH Tally AS
    (
        SELECT TOP (@ThisBatch)
               ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS n
        FROM sys.all_columns a CROSS JOIN sys.all_columns b
    )
    INSERT INTO dbo.LabPayload (Category, Amount, Payload)
    SELECT
        n % 50,
        CAST(n AS decimal(18,4)) / 7.0,
        CASE @Shape
            /* Highly repetitive: a single repeated byte pattern compresses to almost nothing. */
            WHEN N'compressible'
                THEN CAST(REPLICATE(CAST('ABCDEFGH' AS varchar(8)), 1000) AS varbinary(8000))

            /* Cryptographic randomness: no exploitable redundancy, worst-case artifact size. */
            WHEN N'random'
                THEN CRYPT_GEN_RANDOM(8000)

            /*
                Realistic blend: a repetitive text prefix (compresses) concatenated with a
                random tail (does not). Roughly mirrors typical business data, where
                schema-ish text compresses but identifiers and blobs do not.
            */
            ELSE CAST(REPLICATE(CAST('The quick brown fox jumps over the lazy dog. ' AS varchar(45)), 130) AS varbinary(6000))
                 + CRYPT_GEN_RANDOM(2000)
        END
    FROM Tally;

    SET @Inserted += @ThisBatch;

    IF @Inserted % (@BatchRows * 50) = 0
        RAISERROR('  seeded %I64d of %I64d rows', 0, 1, @Inserted, @TargetRows) WITH NOWAIT;
END;
GO

/* Report what was actually produced so the lab can record it as evidence. */
SELECT
    DB_NAME()                                                     AS database_name,
    '$(Shape)'                                                    AS data_shape,
    (SELECT COUNT_BIG(*) FROM dbo.LabPayload)                     AS row_count,
    CAST(SUM(CAST(size AS bigint)) * 8.0 / 1048576.0 AS decimal(18,2)) AS allocated_gb
FROM sys.database_files
WHERE type_desc = 'ROWS';
GO
