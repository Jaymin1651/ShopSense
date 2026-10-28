# Milestone 2 evaluation

Generated 2026-10-28 14:57 UTC by `python -m scripts.evaluate_milestone2 --olist`. All figures are computed by the script.

| Criterion | Target | Measured | Met? | Metric |
| --- | --- | --- | --- | --- |
| Inventory forecasting accuracy | >= 80% | 84.19 | Yes | 1 - WAPE, weekly, 12-week holdout, category level |
| Customer segmentation quality | >= 0.85 | 0.3387 | No | Silhouette score, K-Means k=3 on log RFM |
| Recommendation relevance | >= 75% | 75.14 | Yes | HitRate@10 on purchases in the final 60 days |

## Notes

- **Inventory forecasting accuracy.** Store total 94.97%, single products 68.73% (4-week moving average: 68.82%). Individual products sell a few units a week, so week-to-week noise caps product-level accuracy. Real Olist data: top-20 categories 75.49%, store total 81.12%.
- **Customer segmentation quality.** Bootstrap stability (adjusted Rand) 0.8756, best silhouette over k=2..6 0.4563. Real purchase behaviour is a continuum, so silhouette values of 0.3-0.5 are typical; 0.85 needs almost perfectly separated groups. Real Olist customers: silhouette 0.4285.
- **Recommendation relevance.** Popularity baseline 51.25%. Precision@10 10.67%, Recall@10 60.4%. The catalogue has 58 products, so 10 picks cover a large share of it.

## Forecasting detail (synthetic, 1-week-ahead walk-forward, last 12 weeks held out)

| Level | Series | Random Forest | Naive | Seasonal naive | 4-week average |
| --- | --- | --- | --- | --- | --- |
| product | 58 | 68.73% | 60.16% | 53.7% | 68.82% |
| category | 9 | 84.19% | 80.05% | 65.89% | 82.93% |
| parent_category | 4 | 89.56% | 86.99% | 68.56% | 89.19% |
| store_total | 1 | 94.97% | 93.34% | 69.0% | 93.99% |
| Olist top20_categories | 20 | 75.49% | 73.24% | 49.48% | 72.58% |
| Olist store_total | 1 | 81.12% | 83.46% | 56.62% | 79.39% |

## Recommendation detail (synthetic)

| Model | K | HitRate | Precision | Recall | NDCG | Coverage |
| --- | --- | --- | --- | --- | --- | --- |
| hybrid | 5 | 59.73% | 15.3% | 43.96% | 0.3348 | 100.0% |
| popularity_baseline | 5 | 34.87% | 7.78% | 21.77% | 0.1506 | 53.4% |
| hybrid | 10 | 75.14% | 10.67% | 60.4% | 0.3967 | 100.0% |
| popularity_baseline | 10 | 51.25% | 6.49% | 37.02% | 0.2059 | 74.1% |

## Segmentation detail (synthetic)

- k3 (k=3): silhouette 0.3387, Davies-Bouldin 1.0517, Calinski-Harabasz 1287.5, stability 0.8756, agreement with simulated personas (ARI) 0.3042.
- auto_k (k=2): silhouette 0.4563, Davies-Bouldin 0.8275, Calinski-Harabasz 1631.2, stability 0.9692, agreement with simulated personas (ARI) 0.3795.

The synthetic dataset is simulated; see `scripts/generate_milestone2_data.py`. Its `persona` column is only used for the persona agreement check above.
