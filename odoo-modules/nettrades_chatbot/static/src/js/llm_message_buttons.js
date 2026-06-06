/** @odoo-module **/
// =============================================================================
// NETTRADES Chatbot – Handler for Ask Someone and Good Answer buttons
// =============================================================================
odoo.define('nettrades_chatbot.llm_message_buttons', function (require) {
    "use strict";

    $(document).on('click', '.ask-someone-btn', async function (ev) {
        ev.preventDefault();
        var $btn = $(this);
        var messageId = $btn.data('message-id');
        var question = $btn.data('message-text') || '';

        try {
            var response = await fetch('/api/v1/ask_someone/request', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    artifact_id: messageId,
                    artifact_model: 'llm.message',
                    question: question,
                }),
            });
            var result = await response.json();
            if (result.session_id) {
                window.location.href = '/ask_someone/session/' + result.session_id;
            } else if (result.error) {
                alert(result.error);
            }
        } catch (e) {
            alert('Could not connect to Ask Someone. Please try again.');
        }
    });

    $(document).on('click', '.good-answer-btn', async function (ev) {
        ev.preventDefault();
        var $btn = $(this);
        var messageId = $btn.data('message-id');
        var answererId = $btn.data('answerer-id');
        var fieldId = $btn.data('field-id') || 0;
        var question = $btn.data('question') || '';

        try {
            var response = await fetch('/api/v1/good_answer/vote', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    answer_id: messageId,
                    answer_model: 'llm.message',
                    answerer_id: answererId,
                    field_id: fieldId,
                    question: question,
                }),
            });
            var result = await response.json();
            if (result.success) {
                $btn.prop('disabled', true).text('Thank you!');
            } else {
                alert(result.error || 'Vote failed.');
            }
        } catch (e) {
            alert('Could not record vote. Please try again.');
        }
    });
});