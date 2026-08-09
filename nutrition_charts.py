from __future__ import annotations

from collections.abc import Mapping

import altair as alt
import pandas as pd


CHART_COLORS = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2"]


def stable_line_chart(
    data: pd.DataFrame,
    date_column: str,
    series_labels: Mapping[str, str],
    y_title: str,
    *,
    zero: bool = False,
) -> alt.Chart:
    columns = [date_column, *series_labels]
    chart_data = data.loc[:, columns].copy()
    chart_data[date_column] = pd.to_datetime(chart_data[date_column])
    chart_data = chart_data.melt(
        id_vars=date_column,
        value_vars=list(series_labels),
        var_name="series",
        value_name="value",
    ).dropna(subset=["value"])
    chart_data["indicator"] = chart_data["series"].map(series_labels)

    return (
        alt.Chart(chart_data)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=55), strokeWidth=2.5)
        .encode(
            x=alt.X(
                f"{date_column}:T",
                title="Fecha",
                axis=alt.Axis(format="%d/%m", labelAngle=0),
            ),
            y=alt.Y(
                "value:Q",
                title=y_title,
                scale=alt.Scale(zero=zero),
            ),
            color=alt.Color(
                "indicator:N",
                title=None,
                scale=alt.Scale(range=CHART_COLORS),
            ),
            tooltip=[
                alt.Tooltip(f"{date_column}:T", title="Fecha", format="%d/%m/%Y"),
                alt.Tooltip("indicator:N", title="Indicador"),
                alt.Tooltip("value:Q", title=y_title, format=".1f"),
            ],
        )
        .properties(height=300)
    )
