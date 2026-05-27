import unittest

from lemana_parser.api.normalizers import normalize_api_product


class ApiNormalizerTests(unittest.TestCase):
    def test_normalizes_api_product_to_excel_model(self):
        product = normalize_api_product(
            {
                "productId": "123456",
                "productLink": "/product/test-123456/",
                "displayedName": "Товар",
                "price": {"main_price": 74},
                "mediaMainPhoto": {"desktop": "https://img.example/fallback.png"},
                "characteristics": [
                    {"description": "Цвет", "value": "Белый"},
                    {"description": "Цвет", "value": "Дубль"},
                    {"description": "Материал", "value": "Металл"},
                ],
            },
            {"images": [{"url": "https://img.example/main.png"}]},
        )

        self.assertEqual(product["status"], "ok")
        self.assertEqual(product["article"], "123456")
        self.assertEqual(product["url"], "https://lemanapro.ru/product/test-123456/")
        self.assertEqual(product["name"], "Товар")
        self.assertEqual(product["price"], "74,00")
        self.assertEqual(product["image"], "https://img.example/main.png")
        self.assertEqual(product["characteristics"], {"Цвет": "Белый", "Материал": "Металл"})


if __name__ == "__main__":
    unittest.main()

