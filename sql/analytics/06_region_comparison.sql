-- Compare regions
SELECT region,
       count(DISTINCT video_id)          AS unique_videos,
       count(*)                          AS trending_appearances,
       round(avg(views))                 AS avg_views,
       round(avg(engagement_rate), 4)    AS avg_engagement_rate,
       round(avg(tag_count), 2)          AS avg_tags_per_video
FROM vw_trending
GROUP BY region
ORDER BY trending_appearances DESC;
