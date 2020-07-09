$(function () {
	// Get the form.
	const formClass = '.contact-form';
	const formMessages = $('#form-messages');

	function msg(type, code) {
		let lang = "en";
		let _lang = document.querySelector('html').getAttribute("lang");
		if (!!_lang) {
			lang = _lang;
		}

		const texts = {
			en: {
				errors: {
					"COULD_NOT_SEND": "Your message could not be sent",
					"INVALID_EMAIL": "Invalid email",
					"INCOMPLETE_FORM": "Form incomplete"
				},
				normal: {
					"SENDING": "Sending...",
					"SENT": "Message sent"
				}
			},
			es: {
				errors: {
					"COULD_NOT_SEND": "Su mensaje no pudo ser enviado",
					"INVALID_EMAIL": "Email invalido",
					"INCOMPLETE_FORM": "Formulario incompleto"
				},
				normal: {
					"SENDING": "Enviando...",
					"SENT": "Mensaje enviado"
				}
			}
		}

		const { errors, normal } = texts[lang]

		switch (type) {
			case "normal":
				if (code in normal) {
					return normal[code];
				}
			case "error":
				if (code in errors) {
					return errors[code];
				} else {
					return errors["COULD_NOT_SEND"];
				}
				break;
		}
	}

	function displayMessage(msg, type = "") {
		const [show_class, hide_class] = type == "error" ? ["error", "success"] : ["success", "error"];
		$(formMessages).removeClass(hide_class).addClass(show_class);
		$(formMessages).html(msg);
		setTimeout(() => {
			$(formMessages).removeClass(show_class);
			$(formMessages).html("");
		}, 7000);
	}

	$(formClass).submit(function (e) {
		// Stop the browser from submitting the form.
		e.preventDefault();
		current_form = e.currentTarget;
		const formData = $(e.currentTarget).serializeArray();

		current_form.querySelectorAll('[name]').forEach((e) => e.disabled = true);
		// $(`${formId} :input`).prop("disabled", true);
		const btn_content = current_form.innerHTML;
		// const btn_content = $(`${formId} button`).html();
		// $(`${formId} button`).html("Enviando...");
		current_form.querySelector('button').innerHTML = msg("normal", "SENDING");

		// console.log(formData);
		let formObj = {};
		formData.forEach((field) => {
			formObj[field.name] = field.value;
		});

		let status = 400;

		//get action URL
		const url = current_form.getAttribute('action')
		fetch(url, {
			method: 'POST',
			body: JSON.stringify(formObj),
			headers: new Headers({ 'content-type': 'application/json' }),
			mode: "cors"
		})
			.then((request) => {
				status = request.status;
				return request.json();
			})
			.then((response) => {
				if (status == "200") {
					displayMessage(msg("normal", "SENT"));

					// Clear the form.
					current_form.reset();
				} else if (status == "400") {
					displayMessage(msg("error", response.msg), "error");
				} else {
					displayMessage(msg("error", "COULD_NOT_SEND"), "error");
					// console.log(response);
				}
			})
			.catch((error) => {
				displayMessage(msg("error", "COULD_NOT_SEND"), "error");
				// console.log(error);
			})
			.finally(() => {
				current_form.innerHTML = btn_content;
				current_form.querySelectorAll('[name]').forEach((e) => e.disabled = false);
				// $(`${formId} :input`).prop("disabled", false);
				// $(`${formId} :button`).html(btn_content);
			});

	});

});