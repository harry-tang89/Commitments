def test_home_page(client):
    """
    GIVEN: The Flask app is running in test mode.
    WHEN:  GET / is requested.
    THEN:  The home route responds with HTTP 200.
    """
    # Use Flask's test client to make an HTTP GET request to the home route "/"
    response = client.get("/")

    # Verify the server responded successfully (HTTP 200 OK)
    assert response.status_code == 200
