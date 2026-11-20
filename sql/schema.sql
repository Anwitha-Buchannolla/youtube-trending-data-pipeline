-- Star schema for YouTube trending analytics (DuckDB).
-- Staging tables stg_videos / stg_categories are loaded by pipeline/load.py before this runs.

DROP VIEW  IF EXISTS vw_trending;
DROP TABLE IF EXISTS fact_trending;
DROP TABLE IF EXISTS dim_video;
DROP TABLE IF EXISTS dim_channel;
DROP TABLE IF EXISTS dim_category;
DROP TABLE IF EXISTS dim_region;
DROP TABLE IF EXISTS dim_date;

CREATE TABLE dim_region AS
SELECT row_number() OVER (ORDER BY region) AS region_key, region AS region_code
FROM (SELECT DISTINCT region FROM stg_videos);

CREATE TABLE dim_category AS
SELECT category_id AS category_key, category_name
FROM stg_categories
UNION ALL
-- categories that appear in the data but not in the lookup JSON
SELECT DISTINCT v.category_id, 'Unknown (' || v.category_id || ')'
FROM stg_videos v
WHERE v.category_id IS NOT NULL
  AND v.category_id NOT IN (SELECT category_id FROM stg_categories);

CREATE TABLE dim_channel AS
SELECT row_number() OVER (ORDER BY channel_id) AS channel_key,
       channel_id,
       arg_max(channel_title, trending_day) AS channel_title   -- latest known name
FROM stg_videos
GROUP BY channel_id;

CREATE TABLE dim_video AS
SELECT row_number() OVER (ORDER BY video_id) AS video_key,
       video_id,
       arg_max(title, trending_day)          AS title,
       min(published_at)                     AS published_at,
       arg_max(tags, trending_day)           AS tags,
       arg_max(tag_count, trending_day)      AS tag_count,
       arg_max(thumbnail_link, trending_day) AS thumbnail_link
FROM stg_videos
GROUP BY video_id;

CREATE TABLE dim_date AS
SELECT CAST(strftime(d, '%Y%m%d') AS INTEGER) AS date_key,
       CAST(d AS DATE)                        AS full_date,
       year(d)                                AS year,
       quarter(d)                             AS quarter,
       month(d)                               AS month,
       strftime(d, '%B')                      AS month_name,
       weekofyear(d)                          AS week_of_year,
       isodow(d)                              AS day_of_week,       -- 1 = Monday
       strftime(d, '%A')                      AS day_name,
       isodow(d) >= 6                         AS is_weekend
FROM (SELECT unnest(generate_series(
          (SELECT min(least(trending_day, CAST(published_at AS DATE))) FROM stg_videos),
          (SELECT max(trending_day) FROM stg_videos),
          INTERVAL 1 DAY)) AS d);

CREATE TABLE fact_trending AS
SELECT row_number() OVER (ORDER BY s.trending_day, s.region, s.video_id) AS trending_key,
       v.video_key,
       ch.channel_key,
       s.category_id                                   AS category_key,
       r.region_key,
       CAST(strftime(s.trending_day, '%Y%m%d') AS INTEGER) AS trending_date_key,
       s.views, s.likes, s.dislikes, s.comments,
       s.like_ratio, s.engagement_rate, s.days_to_trend,
       s.publish_hour,
       s.comments_disabled, s.ratings_disabled
FROM stg_videos s
JOIN dim_video   v  ON v.video_id    = s.video_id
JOIN dim_channel ch ON ch.channel_id = s.channel_id
JOIN dim_region  r  ON r.region_code = s.region;

-- Convenience view for ad-hoc analysis / BI tools
CREATE VIEW vw_trending AS
SELECT f.trending_key, d.full_date AS trending_date, d.year, d.month, d.month_name,
       d.day_name, d.is_weekend, r.region_code AS region,
       v.video_id, v.title, ch.channel_title, c.category_name,
       v.published_at, f.publish_hour, f.days_to_trend,
       f.views, f.likes, f.dislikes, f.comments, f.like_ratio, f.engagement_rate,
       v.tag_count, f.comments_disabled, f.ratings_disabled
FROM fact_trending f
JOIN dim_date     d  ON d.date_key    = f.trending_date_key
JOIN dim_region   r  ON r.region_key  = f.region_key
JOIN dim_video    v  ON v.video_key   = f.video_key
JOIN dim_channel  ch ON ch.channel_key = f.channel_key
LEFT JOIN dim_category c ON c.category_key = f.category_key;
