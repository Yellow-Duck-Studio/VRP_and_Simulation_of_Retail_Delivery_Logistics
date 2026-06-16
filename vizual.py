import json
import pandas as pd
import matplotlib.pyplot as plt
import colorcet as cc


def get_colors_many_clusters(n_clusters):
    if n_clusters <= 108:
        colors = cc.glasbey[:n_clusters]
    elif n_clusters <= 256:
        colors = cc.kbc[:n_clusters]
    else:
        colors = []
        while len(colors) < n_clusters:
            colors.extend(cc.glasbey)
        colors = colors[:n_clusters]

    return colors


def visualize_clustering_variant(
        polygon_id: str,
        clustering_variants: dict,
        variant_index: int,
        orders_df: pd.DataFrame,
        warehouses_df: pd.DataFrame,
        figsize: tuple = (12, 8)
):
    """
    Визуализирует все кластеры для выбранного варианта разбиения.

    Параметры:
    - polygon_id: идентификатор полигона (например "task_1")
    - clustering_variants: словарь вида {polygon_id: [variant1, variant2, ...]}
      где variant = list[list[int]] (список кластеров, каждый кластер = список ID заказов)
    - variant_index: индекс варианта разбиения (0, 1, 2...)
    - orders_df: DataFrame с колонками order_id, latitude, longitude, polygon_id
    - warehouses_df: DataFrame с колонками warehouse_id, latitude, longitude, polygon_id
    - figsize: размер фигуры
    """

    # 1. Проверяем существование полигона
    if polygon_id not in clustering_variants:
        raise ValueError(f"Полигон {polygon_id} не найден в clustering_variants")

    variants = clustering_variants[polygon_id]

    polygon_id = int(polygon_id[5:])
    if variant_index >= len(variants):
        raise IndexError(
            f"variant_index={variant_index} превышает количество вариантов ({len(variants)}) для полигона {polygon_id}")

    # 2. Выбираем нужный вариант разбиения
    selected_variant = variants[variant_index]  # список кластеров [[10,3,5], [1,2,4], ...]

    # 3. Фильтруем заказы только для этого полигона
    orders_polygon = orders_df[orders_df['task_id'] == polygon_id]
    if orders_polygon.empty:
        raise ValueError(f"Нет заказов для полигона {polygon_id} в orders_df")

    # 4. Создаём словарь: заказ -> номер кластера (для раскраски)
    order_to_cluster = {}
    for cluster_idx, cluster_orders in enumerate(selected_variant):
        for order_id in cluster_orders:
            order_to_cluster[order_id] = cluster_idx

    # 5. Готовим данные для отрисовки
    # Создаём списки координат для каждого кластера
    cluster_data = {}  # cluster_idx -> {'lats': [], 'lons': []}

    for _, row in orders_polygon.iterrows():
        order_id = row['order_id']
        lat, lon = row['order_lat'], row['order_lon']

        if order_id in order_to_cluster:
            cluster_idx = order_to_cluster[order_id]
            if cluster_idx not in cluster_data:
                cluster_data[cluster_idx] = {'lats': [], 'lons': []}
            cluster_data[cluster_idx]['lats'].append(lat)
            cluster_data[cluster_idx]['lons'].append(lon)
        else:
            # Если заказ не попал ни в один кластер (шум) — помечаем серым
            if -1 not in cluster_data:
                cluster_data[-1] = {'lats': [], 'lons': []}
            cluster_data[-1]['lats'].append(lat)
            cluster_data[-1]['lons'].append(lon)

    # 6. Рисуем
    plt.figure(figsize=figsize)
    plt.grid(True, linestyle='--', alpha=0.3)

    n_clusters = len(selected_variant)
    colors = get_colors_many_clusters(n_clusters)

    # Сначала рисуем "шум" (если есть)
    if -1 in cluster_data:
        plt.scatter(
            cluster_data[-1]['lons'],
            cluster_data[-1]['lats'],
            c='#d9d9d9',
            s=20,
            alpha=0.5,
            label='Не в кластере'
        )

    # Рисуем каждый кластер своим цветом
    for cluster_idx in range(n_clusters):
        if cluster_idx in cluster_data:
            plt.scatter(
                cluster_data[cluster_idx]['lons'],
                cluster_data[cluster_idx]['lats'],
                c=[colors[cluster_idx]],
                s=60,
                alpha=0.8,
                edgecolors='black',
                linewidth=0.5,
                label=f'Кластер {cluster_idx} (n={len(selected_variant[cluster_idx])})'
            )

    warehouses_polygon = warehouses_df[warehouses_df['task_id'] == polygon_id]
    if not warehouses_polygon.empty:
        plt.scatter(
            warehouses_polygon['lon'],
            warehouses_polygon['lat'],
            c='black',
            s=200,
            marker='*',
            edgecolors='gold',
            linewidth=2,
            label='Склады'
        )

        for _, row in warehouses_polygon.iterrows():
            plt.annotate(
                f"WH_{row['warehouse_id']}",
                xy=(row['lon'], row['lat']),
                xytext=(5, 5),
                textcoords='offset points',
                fontsize=8,
                color='black'
            )

    plt.xlabel('Долгота')
    plt.ylabel('Широта')
    plt.title(f'Полигон {polygon_id} — вариант разбиения #{variant_index} (всего кластеров: {n_clusters})')
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    with open('data/master_clusterizations.json', 'r', encoding='utf-8') as file:
        data = json.load(file)

    orders_df = pd.read_csv('data/enriched_orders 2.csv')

    warehouses_data = {
        'warehouse_id': [1, 2],
        'latitude': [55.75, 55.78],
        'longitude': [37.60, 37.65],
        'polygon_id': ['task_1', 'task_1']
    }
    warehouses_df = pd.read_csv('data/enriched_warehouses 2.csv')

    # Вызов функции
    visualize_clustering_variant(
        polygon_id="task_3",
        clustering_variants=data,
        variant_index=2000,
        orders_df=orders_df,
        warehouses_df=warehouses_df
    )
