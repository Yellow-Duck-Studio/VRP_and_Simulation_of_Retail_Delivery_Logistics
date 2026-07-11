import json
import sys
import argparse
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
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


# Стиль линии маршрута в зависимости от типа транспорта
TRANSPORT_LINESTYLE = {
    'foot': ':',
    'bike': '--',
    'car': '-',
}


def find_task_record(solutions: list, task_num: int):
    """
    Ищет запись решения по числовому task_id (сравнение приводится к строке,
    т.к. в JSON task_id хранится как строка).
    """
    target = str(task_num)
    for rec in solutions:
        if str(rec.get('task_id')) == target:
            return rec
    return None


def visualize_task_solution(
        task_num: int,
        solutions: list,
        orders_df: pd.DataFrame,
        warehouses_df: pd.DataFrame,
        draw_routes: bool = True,
        figsize: tuple = (12, 8)
):
    """
    Визуализирует решение (набор кластеров-маршрутов) для одной задачи (task_id).
    """

    # 1. Находим запись по task_id
    record = find_task_record(solutions, task_num)
    if record is None:
        raise ValueError(f"Задача task_id={task_num} не найдена в переданных решениях")

    clusters = record.get('clusters', [])
    if not clusters:
        raise ValueError(f"Для task_id={task_num} список clusters пуст")

    task_numeric_id = task_num
    warehouse_id = record.get('warehouse_id')

    # 2. Фильтруем заказы только для этого полигона
    orders_polygon = orders_df[orders_df['task_id'] == task_numeric_id]
    if orders_polygon.empty:
        raise ValueError(f"Нет заказов для полигона {task_numeric_id} в orders_df")

    # Быстрый доступ к координатам заказа по order_id (приводим к строке, как в JSON)
    orders_polygon = orders_polygon.copy()
    orders_polygon['order_id'] = orders_polygon['order_id'].astype(str)
    coord_lookup = orders_polygon.set_index('order_id')[['order_lat', 'order_lon']].to_dict('index')

    # 3. Готовим данные для отрисовки: cluster_idx -> {'lats', 'lons', 'transport', 'feasible', 'order_ids', 'order_sequence'}
    cluster_data = {}
    order_to_cluster = {}

    for cluster_idx, cluster in enumerate(clusters):
        order_ids = [str(o) for o in cluster.get('order_ids', [])]
        for oid in order_ids:
            order_to_cluster[oid] = cluster_idx

        lats, lons = [], []
        for oid in order_ids:
            if oid in coord_lookup:
                lats.append(coord_lookup[oid]['order_lat'])
                lons.append(coord_lookup[oid]['order_lon'])

        cluster_data[cluster_idx] = {
            'lats': lats,
            'lons': lons,
            'transport': cluster.get('transport', 'unknown'),
            'feasible': cluster.get('feasible', True),
            'order_ids': order_ids,
            'order_sequence': [str(o) for o in cluster.get('order_sequence', order_ids)],
        }

    # Заказы, не попавшие ни в один кластер (на всякий случай)
    noise_lats, noise_lons = [], []
    for _, row in orders_polygon.iterrows():
        if row['order_id'] not in order_to_cluster:
            noise_lats.append(row['order_lat'])
            noise_lons.append(row['order_lon'])

    # 4. Рисуем
    plt.figure(figsize=figsize)
    plt.grid(True, linestyle='--', alpha=0.3)

    n_clusters = len(clusters)
    colors = get_colors_many_clusters(max(n_clusters, 1))

    if noise_lats:
        plt.scatter(
            noise_lons, noise_lats,
            c='#d9d9d9', s=20, alpha=0.5, label='Не в кластере'
        )

    for cluster_idx, data in cluster_data.items():
        color = colors[cluster_idx]
        feasible = data['feasible']
        n_orders = len(data['order_ids'])

        # Точки заказов
        plt.scatter(
            data['lons'], data['lats'],
            c=[color], s=60, alpha=0.85,
            edgecolors=('red' if not feasible else 'black'),
            linewidth=(1.8 if not feasible else 0.5),
            marker=('x' if not feasible else 'o'),
            label=(
                f"Кластер {cluster_idx} | {data['transport']} | n={n_orders}"
                + ('' if feasible else ' | НЕФИЗИБЛ')
            )
        )

        # Маршрут по order_sequence
        if draw_routes and len(data['order_sequence']) > 1:
            seq_lats, seq_lons = [], []
            for oid in data['order_sequence']:
                if oid in coord_lookup:
                    seq_lats.append(coord_lookup[oid]['order_lat'])
                    seq_lons.append(coord_lookup[oid]['order_lon'])
            linestyle = TRANSPORT_LINESTYLE.get(data['transport'], '-')
            plt.plot(
                seq_lons, seq_lats,
                color=color, linestyle=linestyle, linewidth=1.5, alpha=0.7, zorder=1
            )

    # Склад(ы)
    warehouses_polygon = warehouses_df[warehouses_df['task_id'] == task_numeric_id]
    if warehouse_id is not None and 'warehouse_id' in warehouses_polygon.columns:
        matched = warehouses_polygon[
            warehouses_polygon['warehouse_id'].astype(str) == str(warehouse_id)
        ]
        if not matched.empty:
            warehouses_polygon = matched

    if not warehouses_polygon.empty:
        plt.scatter(
            warehouses_polygon['lon'],
            warehouses_polygon['lat'],
            c='black', s=200, marker='*',
            edgecolors='gold', linewidth=2, label='Склад'
        )
        for _, row in warehouses_polygon.iterrows():
            plt.annotate(
                f"WH_{row['warehouse_id']}",
                xy=(row['lon'], row['lat']),
                xytext=(5, 5), textcoords='offset points',
                fontsize=8, color='black'
            )

    # Легенда стилей линий (типы транспорта), отдельно от кластеров, чтобы не раздувать основную легенду
    transport_handles = [
        mlines.Line2D([], [], color='gray', linestyle=ls, label=f'Маршрут: {t}')
        for t, ls in TRANSPORT_LINESTYLE.items()
    ]

    cluster_legend = plt.legend(loc='upper left', bbox_to_anchor=(1.02, 1.0), fontsize=8, title='Кластеры')
    plt.gca().add_artist(cluster_legend)
    plt.legend(handles=transport_handles, loc='lower left', bbox_to_anchor=(1.02, 0.0), fontsize=8)

    total_cost = record.get('total_cost')
    overall_feasible = record.get('feasible')
    plt.xlabel('Долгота')
    plt.ylabel('Широта')
    plt.title(
        f"task_id={task_numeric_id} | кластеров: {n_clusters} | "
        f"total_cost={total_cost} | feasible={overall_feasible}"
    )
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Визуализация решения (кластеров-маршрутов) для задачи.")
    parser.add_argument("task_num", type=int, help="Номер задачи (task_id), например 1")
    parser.add_argument("--solutions", type=str, default="predictions.json",
                        help="Путь к JSON-файлу решений (список записей с task_id/clusters). По умолчанию solutions.json")
    parser.add_argument("--no-routes", action="store_true",
                        help="Не рисовать линии маршрутов (order_sequence), только точки заказов")

    args = parser.parse_args()

    print("Загрузка данных...")
    with open(args.solutions, 'r', encoding='utf-8') as file:
        solutions = json.load(file)

    if not isinstance(solutions, list):
        print(
            f"Ошибка: ожидался список записей (решений) в {args.solutions}, "
            f"получен {type(solutions)}",
            file=sys.stderr
        )
        sys.exit(1)

    orders_df = pd.read_csv('data/large/orders-L.csv')
    warehouses_df = pd.read_csv('data/large/warehouses-L.csv')

    try:
        visualize_task_solution(
            task_num=args.task_num,
            solutions=solutions,
            orders_df=orders_df,
            warehouses_df=warehouses_df,
            draw_routes=not args.no_routes,
        )
    except (ValueError, IndexError) as e:
        print(f"Ошибка при визуализации: {e}", file=sys.stderr)
        sys.exit(1)