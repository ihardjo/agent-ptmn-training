import { chatRouter } from './routes/chat';
import { historyRouter } from './routes/history';
import { sessionRouter } from './routes/session';
import { messagesRouter } from './routes/messages';
import { configRouter } from './routes/config';
import { feedbackRouter } from './routes/feedback';

const app: Express = express();

// API routes
app.use('/api/chat', chatRouter);
app.use('/api/history', historyRouter);
app.use('/api/session', sessionRouter);
app.use('/api/messages', messagesRouter);
app.use('/api/config', configRouter);
app.use('/api/feedback', feedbackRouter);
