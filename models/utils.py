def dict_from_row(row, columns):
    if isinstance(row, dict):
        return row
    return dict(zip(columns, row))