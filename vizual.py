import json
import sys
import argparse
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
    """

    # 1. Проверяем существование полигона
    if polygon_id not in clustering_variants:
        raise ValueError(f"Полигон {polygon_id} не найден в clustering_variants")

    variants = clustering_variants[polygon_id]
    
    # Защита от выхода за границы, если индекс передали вручную
    if variant_index >= len(variants) or variant_index < -len(variants):
        raise IndexError(
            f"variant_index={variant_index} выходит за пределы диапазона. "
            f"Доступно вариантов для {polygon_id}: {len(variants)} (индексы от 0 до {len(variants) - 1})"
        )

    # 2. Выбираем нужный вариант разбиения
    selected_variant = variants[variant_index]  # список кластеров [[10,3,5], [1,2,4], ...]

    # Для заголовка и фильтров получаем чистый числовой ID
    try:
        task_numeric_id = int(polygon_id.split('_')[1])
    except (IndexError, ValueError):
        task_numeric_id = polygon_id

    # 3. Фильтруем заказы только для этого полигона
    orders_polygon = orders_df[orders_df['task_id'] == task_numeric_id]
    if orders_polygon.empty:
        raise ValueError(f"Нет заказов для полигона {task_numeric_id} в orders_df")

    # 4. Создаём словарь: заказ -> номер кластера (для раскраски)
    order_to_cluster = {}
    for cluster_idx, cluster_orders in enumerate(selected_variant):
        for order_id in cluster_orders:
            order_to_cluster[order_id] = cluster_idx

    # 5. Готовим данные для отрисовки
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

    warehouses_polygon = warehouses_df[warehouses_df['task_id'] == task_numeric_id]
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

    # Корректно отображаем реальный индекс (даже если передали -1 для последнего)
    actual_index = variant_index if variant_index >= 0 else len(variants) + variant_index

    plt.xlabel('Долгота')
    plt.ylabel('Широта')
    plt.title(f'Полигон {polygon_id} — вариант разбиения #{actual_index} (всего кластеров: {n_clusters})')
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    # Настраиваем парсер аргументов командной строки
    parser = argparse.ArgumentParser(description="Визуализация разбиений кластеров для задач.")
    
    # Первый обязательный аргумент: номер задачи
    parser.add_argument("task_num", type=int, help="Номер задачи (например, 1 для task_1)")
    
    # Второй опциональный аргумент: индекс разбиения. Если не указан, по умолчанию None
    parser.add_argument("variant_idx", type=int, nargs="?", default=None, 
                        help="Индекс разбиения. Если не указан, берется последнее существующее.")

    args = parser.parse_args()

    # Формируем polygon_id
    polygon_id = f"task_{args.task_num}"

    # Загружаем данные
    print("Загрузка данных...")
    with open('data/master_clusterizations.json', 'r', encoding='utf-8') as file:
        clustering_variants = json.load(file)

    orders_df = pd.read_csv('data/orders.csv')
    warehouses_df = pd.read_csv('data/warehouses.csv')

    # Проверяем наличие задачи в JSON
    if polygon_id not in clustering_variants:
        print(f"Ошибка: Задача {polygon_id} не найдена в master_clusterizations.json", file=sys.stderr)
        sys.exit(1)

    variants = clustering_variants[polygon_id]
    total_variants = len(variants)
    print(f"Для {polygon_id} найдено всего вариантов разбиений: {total_variants}")

    # Определяем нужный индекс разбиения
    if args.variant_idx is None:
        # Если параметр не передан — берем последний (индекс -1)
        variant_index = -1
        print(f"Параметр variant_index не указан. Автоматически выбрано последнее разбиение (индекс {total_variants - 1}).")
    else:
        variant_index = args.variant_idx
        print(f"Запрошено конкретное разбиение с индексом: {variant_index}")

    # Вызов функции визуализации с обработкой возможных исключений по индексам
    try:
        visualize_clustering_variant(
            polygon_id=polygon_id,
            clustering_variants=clustering_variants,
            variant_index=variant_index,
            orders_df=orders_df,
            warehouses_df=warehouses_df
        )
    except (ValueError, IndexError) as e:
        print(f"Ошибка при визуализации: {e}", file=sys.stderr)
        sys.exit(1)
