import errorHtml from '../assets/error/index.html';
import { safeError } from '@common';

export async function renderError(error: any): Promise<Response> {
    try {
        const html = errorHtml
            .replace('__ERROR_MESSAGE__', safeError(error))
            .replaceAll('__ICON__', '');

        return new Response(html, {
            headers: { 'Content-Type': 'text/html; charset=utf-8' }
        });
    } catch (err) {
        return new Response(`Error: ${safeError(error)}`, {
            headers: { 'Content-Type': 'text/plain; charset=utf-8' }
        });
    }
}
