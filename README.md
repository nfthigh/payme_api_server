# Payme Merchant API server


## Description

This project is a simple API server that allows merchants to accept payments from customers using the Payme payment gateway. It provides two endpoints: one for the Payme merchant callback and another for the payment request and generating the payment URL.
payme develop documentation [here](https://developer.help.paycom.uz/protokol-merchant-api/)

## Installation

To install this project, follow these steps:

1. Clone the repository  
2. Navigate to the project directory
3. Install dependencies: `pip3 install -r requirements.txt`
4. create your own .env file and add the following variables
```bash
POSTGRES_PASSWORD=postgres
POSTGRES_USER=postgres
POSTGRES_DB=postgres
POSTGRES_HOST=speaklish_db
POSTGRES_PORT=5432
DB_URL=postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}



#payme settings
PAYME_KEY='KybcMW2oZfn3C6QDi9Sx**********'
PAYME_TEST_KEY='KybcMW2oZfn3C6QDi9Sx**********'
PAYME_ID='64d088c8a8a1f************'
PAYME_URL=https://checkout.paycom.uz
PAYME_TEST_URL=https://test.paycom.uz
PAYME_MIN_AMOUNT=100
PAYME_ACCOUNT=order_id



#docker settings
DOCKER_IMAGE_NAME=payme_image
DOCKER_CONTAINER_NAME=payme_merchant_API
DOCKER_PORT=8080

DB_CONTAINER_NAME=speaklish_db
```


## Usage

To use this project, follow these steps:

simply run with docker
```bash
docker-compose up
```

it has 2 endpoints
1. /payme/   # for payme merchant callback 
2. /payment/ # for payment request and gerating payment url

to test go to http://localhost:port/docs


## Contributing

Contributions are welcome! Please follow these guidelines when contributing to the project:

1. Fork the repository.
2. Create a new branch: `git checkout -b feature/your-feature`
3. Make your changes and commit them: `git commit -m 'Add your commit message'`
4. Push to the branch: `git push origin feature/your-feature`
5. Submit a pull request.

## License

This project is licensed under the [MIT License](LICENSE).

## Contact

For any questions or inquiries, please contact the project maintainer at mardonovbobir9@gmail.com
