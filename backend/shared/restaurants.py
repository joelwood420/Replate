def upsert_restaurant(
    restaurant_id: str,
    name: str,
    address: str,
    latitude: float,
    longitude: float,
    menu_source_url: str | None,
    conn,
) -> None:
    """Insert a Restaurants row if one doesn't already exist for restaurant_id.

    Deliberately WHEN NOT MATCHED only (no UPDATE on match) - a restaurant
    that already has a cached menu (MenuSourceUrl/MenuLastFetchedAt from a
    prior fetch_restaurant_menu run) must not have those fields silently
    clobbered just because the restaurant was selected/geocoded again.
    """
    cursor = conn.cursor()
    cursor.execute(
        "MERGE Restaurants AS target USING (SELECT ? AS RestaurantId) AS src "
        "ON target.RestaurantId = src.RestaurantId "
        "WHEN NOT MATCHED THEN INSERT (RestaurantId, Name, Address, Latitude, Longitude, MenuSourceUrl) "
        "VALUES (?, ?, ?, ?, ?, ?);",
        restaurant_id,
        restaurant_id,
        name,
        address,
        latitude,
        longitude,
        menu_source_url,
    )
