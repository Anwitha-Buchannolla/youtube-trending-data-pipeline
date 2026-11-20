-- Top 20 videos by peak view count reached while trending
SELECT title, channel_title, category_name, region,
       max(views)                  AS peak_views,
       count(*)                    AS days_trending,
       round(avg(engagement_rate), 4) AS avg_engagement
FROM vw_trending
GROUP BY video_id, title, channel_title, category_name, region
ORDER BY peak_views DESC
LIMIT 20;
