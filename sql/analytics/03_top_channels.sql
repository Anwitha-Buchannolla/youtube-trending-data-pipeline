-- Channels that most often reach the trending list
SELECT channel_title,
       count(DISTINCT video_id) AS trending_videos,
       count(*)                 AS trending_appearances,
       sum(views)               AS cumulative_daily_views,
       round(avg(engagement_rate), 4) AS avg_engagement_rate
FROM vw_trending
GROUP BY channel_title
ORDER BY trending_videos DESC, trending_appearances DESC
LIMIT 20;
