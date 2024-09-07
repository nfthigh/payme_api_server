CREATE TABLE public.orders (
    order_id integer NOT NULL,
    user_id bigint NOT NULL,
    price double precision NOT NULL,
    session_quantity integer NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone
);






--
-- Name: payme_transactions; Type: TABLE; Schema: public;
--

CREATE TABLE public.payme_transactions (
    id character varying(255) NOT NULL,
    transaction_id character varying(255) NOT NULL,
    order_id bigint NOT NULL,
    amount double precision,
    "time" bigint,
    perform_time bigint,
    cancel_time bigint,
    state integer,
    reason character varying(255),
    created_at_ms bigint,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);





--
-- Name: orders orders_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (order_id);


--
-- PostgreSQL database dump complete
--

