-- Which categories trend most, and how well do they engage audiences?
SELECT category_name,
       count(DISTINCT video_id)          AS unique_videos,
       count(*)                          AS trending_appearances,
       round(avg(views))                 AS avg_views,
       round(avg(like_ratio), 4)         AS avg_like_ratio,
       round(avg(engagement_rate), 4)    AS avg_engagement_rate
FROM vw_trending
GROUP BY category_name
ORDER BY trending_appearances DESC;
